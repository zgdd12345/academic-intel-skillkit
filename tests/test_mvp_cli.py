from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import common
import fetch_arxiv
import fetch_huggingface
import run_daily_pipeline


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class MvpCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workdir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_config(self, arxiv_enabled: bool = True) -> Path:
        config_path = self.workdir / "research-topics.local.yaml"
        config_path.write_text(
            textwrap.dedent(
                f"""
                obsidian:
                  vault_path: "/tmp/ObsidianVault"
                  root_dir: "Research_Intel"

                reporting:
                  daily_top_n: 5
                  daily_detailed_top_n: 2

                sources:
                  arxiv:
                    enabled: {"true" if arxiv_enabled else "false"}
                    lookback_days: 7
                    max_results_per_topic: 10
                    topic_ids: []

                topics:
                  - id: agents
                    name: AI Agents
                    enabled: true
                    priority: high
                    include_keywords:
                      - agent
                      - multi-agent
                      - tool use
                    exclude_keywords:
                      - game agent
                    arxiv_categories:
                      - cs.AI
                      - cs.LG

                  - id: multimodal
                    name: Multimodal Systems
                    enabled: true
                    priority: medium
                    include_keywords:
                      - multimodal
                      - vision-language
                    exclude_keywords: []
                    arxiv_categories:
                      - cs.CV
                      - cs.CL
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        return config_path

    def write_arxiv_payload(self) -> Path:
        now = datetime.now(timezone.utc)
        payload_path = self.workdir / "arxiv.json"
        payload = {
            "generated_at": now.isoformat(),
            "mode": "config",
            "items": [
                {
                    "source": "arXiv",
                    "title": "Tool-Using Multi-Agent Planning",
                    "url": "https://arxiv.org/abs/2603.00001",
                    "summary": "A planning paper about multi-agent tool use for complex tasks.",
                    "summary_zh": "提出一个面向复杂任务的多智能体工具使用规划框架。",
                    "authors": ["Alice Zhang", "Bob Li"],
                    "paper_id": "2603.00001",
                    "published_at": (now - timedelta(days=1)).isoformat(),
                    "categories": ["cs.AI", "cs.LG"],
                },
                {
                    "source": "arXiv",
                    "title": "Vision-Language Evaluation without Translation",
                    "url": "https://arxiv.org/abs/2603.00002",
                    "summary": "This work studies evaluation signals for vision-language systems.",
                    "authors": ["Carol Wu"],
                    "paper_id": "2603.00002",
                    "published_at": (now - timedelta(days=2)).isoformat(),
                    "categories": ["cs.CV", "cs.CL"],
                },
            ],
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload_path

    def write_invalid_json(self, file_name: str, content: str = "{") -> Path:
        path = self.workdir / file_name
        path.write_text(content, encoding="utf-8")
        return path

    def write_huggingface_payload(self) -> Path:
        payload_path = self.workdir / "huggingface.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "Hugging Face Papers",
            "items": [
                {
                    "source": "Hugging Face Papers",
                    "title": "Reward-Guided Agent Search",
                    "url": "https://huggingface.co/papers/2603.10001",
                    "note_zh": "Hugging Face 热榜第 1 位，主要对应 AI Agents 方向，社区信号为 42 个点赞、5 条评论。建议结合原摘要、评论区和外链快速判断是否纳入跟踪。",
                    "matched_topics": ["agents"],
                    "rank": 1,
                    "upvotes": 42,
                    "num_comments": 5,
                }
            ],
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload_path

    def write_diagnostic_config(self) -> Path:
        config_path = self.workdir / "diagnostic-topics.local.yaml"
        config_path.write_text(
            textwrap.dedent(
                """
                obsidian:
                  vault_path: "/tmp/ObsidianVault"
                  root_dir: "Research_Intel"

                reporting:
                  daily_top_n: 5
                  daily_detailed_top_n: 2

                sources:
                  arxiv:
                    enabled: true
                    lookback_days: 3
                    max_results_per_topic: 12
                    topic_ids:
                      - dense

                topics:
                  - id: dense
                    name: Dense Topic
                    enabled: true
                    priority: high
                    include_keywords:
                      - one
                      - two
                      - three
                      - four
                      - five
                      - six
                      - seven
                    exclude_keywords:
                      - noise-one
                      - noise-two
                      - noise-three
                      - noise-four
                      - noise-five
                      - noise-six
                      - noise-seven
                    arxiv_categories:
                      - cs.AI

                  - id: sparse
                    name: Sparse Topic
                    enabled: true
                    priority: medium
                    include_keywords: []
                    exclude_keywords: []
                    arxiv_categories: []

                  - id: disabled
                    name: Disabled Topic
                    enabled: false
                    priority: low
                    include_keywords:
                      - archive
                    exclude_keywords: []
                    arxiv_categories:
                      - cs.CL
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        return config_path

    def test_generate_daily_brief_renders_chinese_sections(self) -> None:
        config_path = self.write_config()
        arxiv_path = self.write_arxiv_payload()
        out_path = self.workdir / "daily-brief.md"

        result = run_cli(
            "scripts/generate_daily_brief.py",
            "--config",
            str(config_path),
            "--arxiv",
            str(arxiv_path),
            "--semantic-scholar",
            str(self.workdir / "missing-semantic-scholar.json"),
            "--huggingface",
            str(self.workdir / "missing-hotspots.json"),
            "--out",
            str(out_path),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("已写入日报", result.stdout)
        self.assertIn("警告：未找到可选输入 Semantic Scholar", result.stderr)
        self.assertIn("警告：未找到可选输入 社区热点", result.stderr)

        content = out_path.read_text(encoding="utf-8")
        self.assertIn("# 研究情报日报 ·", content)
        self.assertIn("[!abstract] 今日概览", content)
        self.assertIn("## 最新工作", content)
        self.assertIn("提出一个面向复杂任务的多智能体工具使用规划框架。", content)
        self.assertIn("中文导读：", content)
        self.assertIn("当前稳定实现链路是 arXiv 抓取、归一化去重、主题匹配评分和 Markdown 日报渲染。", content)
        self.assertIn("指定了 Semantic Scholar JSON，但当前文件不存在，因此本次没有合并该输入。", content)
        self.assertIn("指定了社区热点 JSON，但当前文件不存在，因此该板块只保留空状态说明。", content)

    def test_generate_daily_brief_renders_hotspot_note_when_payload_exists(self) -> None:
        config_path = self.write_config()
        arxiv_path = self.write_arxiv_payload()
        hotspot_path = self.write_huggingface_payload()
        out_path = self.workdir / "daily-brief.md"

        result = run_cli(
            "scripts/generate_daily_brief.py",
            "--config",
            str(config_path),
            "--arxiv",
            str(arxiv_path),
            "--semantic-scholar",
            str(self.workdir / "missing-semantic-scholar.json"),
            "--huggingface",
            str(hotspot_path),
            "--out",
            str(out_path),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("Reward-Guided Agent Search", content)
        self.assertIn("热榜第 1 位", content)
        self.assertIn("已合并社区热点 JSON；当前仓库已提供最小可用的 `scripts/fetch_huggingface.py` 采集器。", content)

    def test_manage_topics_outputs_chinese_list_validate_and_detail(self) -> None:
        config_path = self.write_config()

        list_result = run_cli("scripts/manage_topics.py", "--config", str(config_path), "--list")
        self.assertEqual(list_result.returncode, 0, msg=list_result.stderr)
        self.assertIn("主题总览", list_result.stdout)
        self.assertIn("包含关键词=3", list_result.stdout)

        validate_result = run_cli("scripts/manage_topics.py", "--config", str(config_path), "--validate")
        self.assertEqual(validate_result.returncode, 0, msg=validate_result.stdout + validate_result.stderr)
        self.assertIn("配置概览：", validate_result.stdout)
        self.assertIn("topic 总数=2 | 启用=2 | 停用=0", validate_result.stdout)
        self.assertIn("配置校验通过。", validate_result.stdout)

        query_plan_result = run_cli("scripts/manage_topics.py", "--config", str(config_path), "--query-plan")
        self.assertEqual(query_plan_result.returncode, 0, msg=query_plan_result.stderr)
        self.assertIn("arXiv 抓取计划", query_plan_result.stdout)
        self.assertIn("lookback_days=7 | max_results_per_topic=10", query_plan_result.stdout)
        self.assertIn("实际纳入查询的 topic 数=2", query_plan_result.stdout)
        self.assertIn("agents | 名称=AI Agents | 包含关键词=3/3 | 排除关键词=1/1 | 分类=2", query_plan_result.stdout)
        self.assertIn("multimodal | 名称=Multimodal Systems | 包含关键词=2/2 | 排除关键词=0/0 | 分类=2", query_plan_result.stdout)
        self.assertIn("查询=(all:agent OR all:\"multi-agent\" OR all:\"tool use\") AND (cat:cs.AI OR cat:cs.LG) ANDNOT (all:\"game agent\")", query_plan_result.stdout)
        self.assertIn("ANDNOT", query_plan_result.stdout)

        detail_result = run_cli(
            "scripts/manage_topics.py",
            "--config",
            str(config_path),
            "--detail",
            "--topic",
            "agents",
        )
        self.assertEqual(detail_result.returncode, 0, msg=detail_result.stderr)
        self.assertIn("主题：agents", detail_result.stdout)
        self.assertIn("名称：AI Agents", detail_result.stdout)
        self.assertIn("包含关键词：agent, multi-agent, tool use", detail_result.stdout)

        filtered_query_plan_result = run_cli(
            "scripts/manage_topics.py",
            "--config",
            str(config_path),
            "--query-plan",
            "--topic",
            "agents",
        )
        self.assertEqual(filtered_query_plan_result.returncode, 0, msg=filtered_query_plan_result.stderr)
        self.assertIn("生效 topic 过滤：agents", filtered_query_plan_result.stdout)
        self.assertIn("agents | 名称=AI Agents | 包含关键词=3/3 | 排除关键词=1/1 | 分类=2", filtered_query_plan_result.stdout)
        self.assertNotIn("multimodal | 名称=Multimodal Systems | 查询=", filtered_query_plan_result.stdout)

    def test_manage_topics_diagnose_surfaces_scope_and_truncation(self) -> None:
        config_path = self.write_diagnostic_config()

        result = run_cli("scripts/manage_topics.py", "--config", str(config_path), "--diagnose")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("主题：dense", result.stdout)
        self.assertIn("arXiv 抓取：纳入默认抓取", result.stdout)
        self.assertIn("包含关键词：7 个（实际进入查询 6 个，截断 1 个）", result.stdout)
        self.assertIn("排除关键词：7 个（实际进入查询 6 个，截断 1 个）", result.stdout)
        self.assertIn("包含关键词共 7 个，但 arXiv 查询只会使用前 6 个。", result.stdout)
        self.assertIn("主题：sparse", result.stdout)
        self.assertIn("arXiv 抓取：未纳入抓取：不在 sources.arxiv.topic_ids 范围内", result.stdout)
        self.assertIn("未配置包含关键词或 arXiv 分类；查询会回退到默认 `cat:cs.AI`，相关性较弱。", result.stdout)
        self.assertIn("主题：disabled", result.stdout)
        self.assertIn("arXiv 抓取：未纳入抓取：当前 topic 已停用", result.stdout)

    def test_fetch_arxiv_can_exit_cleanly_without_network_when_disabled(self) -> None:
        config_path = self.write_config(arxiv_enabled=False)
        out_path = self.workdir / "disabled-arxiv.json"

        result = run_cli(
            "scripts/fetch_arxiv.py",
            "--config",
            str(config_path),
            "--out",
            str(out_path),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("已写入 0 条 arXiv 候选到", result.stdout)

        payload = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["mode"], "config")

    def test_enrich_target_arxiv_dry_run(self) -> None:
        config_path = self.write_config()
        arxiv_path = self.write_arxiv_payload()
        result = run_cli(
            "scripts/enrich_summaries.py",
            "--config", str(config_path),
            "--arxiv", str(arxiv_path),
            "--enrich-target", "arxiv",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("dry-run", result.stdout)

    def test_enrich_target_huggingface_dry_run_skips_arxiv(self) -> None:
        config_path = self.write_config()
        arxiv_path = self.write_arxiv_payload()
        hf_path = self.write_huggingface_payload()
        result = run_cli(
            "scripts/enrich_summaries.py",
            "--config", str(config_path),
            "--arxiv", str(arxiv_path),
            "--huggingface", str(hf_path),
            "--enrich-target", "huggingface",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # Should NOT contain arXiv shortlist output
        self.assertNotIn("shortlist=", result.stdout)

    def test_generate_daily_brief_fails_on_invalid_required_arxiv_json(self) -> None:
        config_path = self.write_config()
        arxiv_path = self.write_invalid_json("broken-arxiv.json", "{invalid")
        out_path = self.workdir / "daily-brief.md"

        result = run_cli(
            "scripts/generate_daily_brief.py",
            "--config",
            str(config_path),
            "--arxiv",
            str(arxiv_path),
            "--out",
            str(out_path),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("JSON 解析失败", result.stderr)
        self.assertFalse(out_path.exists())


class ReviewRegressionTests(unittest.TestCase):
    def test_obsidian_daily_brief_path_uses_config(self) -> None:
        config = {
            "obsidian": {
                "vault_path": "/tmp/ObsidianVault",
                "root_dir": "Research_Intel",
            }
        }

        path = common.obsidian_daily_brief_path(config, "2026-03-13")

        self.assertEqual(
            path,
            Path("/tmp/ObsidianVault/Research_Intel/01_Daily/2026-03/2026_03_13_Daily.md"),
        )

    def _make_pipeline_config(self, workdir: Path) -> Path:
        config_path = workdir / "research-topics.local.yaml"
        config_path.write_text(
            textwrap.dedent(
                """
                obsidian:
                  vault_path: "/tmp/ObsidianVault"
                  root_dir: "Research_Intel"
                reporting:
                  daily_top_n: 5
                  daily_detailed_top_n: 2
                sources:
                  arxiv:
                    enabled: true
                    lookback_days: 2
                    max_results_per_topic: 10
                    topic_ids: []
                topics:
                  - id: agents
                    name: AI Agents
                    enabled: true
                    priority: high
                    include_keywords:
                      - agent
                    exclude_keywords: []
                    arxiv_categories:
                      - cs.AI
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        return config_path

    def test_run_daily_pipeline_serial_sequences_commands_and_uses_obsidian_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            config_path = self._make_pipeline_config(workdir)

            completed = subprocess.CompletedProcess(args=[], returncode=0)
            with patch("run_daily_pipeline.subprocess.run", return_value=completed) as mock_run, patch(
                "run_daily_pipeline.sys.argv",
                [
                    "run_daily_pipeline.py",
                    "--config",
                    str(config_path),
                    "--date",
                    "2026-03-13",
                    "--topic",
                    "agents",
                    "--no-parallel",
                ],
            ):
                run_daily_pipeline.main()

            # Serial pipeline runs 4 steps: arXiv → multi-source → enrich → brief
            self.assertEqual(mock_run.call_count, 4)
            arxiv_cmd = mock_run.call_args_list[0].args[0]
            hotspot_cmd = mock_run.call_args_list[1].args[0]
            enrich_cmd = mock_run.call_args_list[2].args[0]
            brief_cmd = mock_run.call_args_list[3].args[0]

            self.assertIn("fetch_arxiv.py", arxiv_cmd[1])
            self.assertIn("--topic", arxiv_cmd)
            self.assertIn("agents", arxiv_cmd)
            self.assertIn("run_multi_source.py", hotspot_cmd[1])
            self.assertIn("enrich_summaries.py", enrich_cmd[1])
            self.assertIn("generate_daily_brief.py", brief_cmd[1])
            self.assertIn(
                "/tmp/ObsidianVault/Research_Intel/01_Daily/2026-03/2026_03_13_Daily.md",
                brief_cmd,
            )

    def test_run_daily_pipeline_parallel_uses_popen_for_fetch_and_enrich(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            config_path = self._make_pipeline_config(workdir)

            completed = subprocess.CompletedProcess(args=[], returncode=0)
            popen_calls: list[list[str]] = []

            def fake_popen(cmd: list[str], **_kw: object) -> Mock:
                popen_calls.append(cmd)
                return Mock(wait=Mock(return_value=0), poll=Mock(return_value=0))

            with patch("run_daily_pipeline.subprocess.Popen", side_effect=fake_popen), \
                 patch("run_daily_pipeline.subprocess.run", return_value=completed) as mock_run, \
                 patch(
                     "run_daily_pipeline.sys.argv",
                     [
                         "run_daily_pipeline.py",
                         "--config",
                         str(config_path),
                         "--date",
                         "2026-03-13",
                         "--topic",
                         "agents",
                     ],
                 ):
                run_daily_pipeline.main()

            # Phase 1: 2 Popen calls (arXiv fetch + multi-source fetch)
            # Phase 2: 2 Popen calls (arXiv enrich + HF enrich)
            # Phase 3: 1 subprocess.run call (brief generation)
            self.assertEqual(len(popen_calls), 4)
            self.assertIn("fetch_arxiv.py", popen_calls[0][1])
            self.assertIn("run_multi_source.py", popen_calls[1][1])
            self.assertIn("enrich_summaries.py", popen_calls[2][1])
            self.assertIn("--enrich-target", popen_calls[2])
            self.assertIn("arxiv", popen_calls[2])
            self.assertIn("enrich_summaries.py", popen_calls[3][1])
            self.assertIn("--enrich-target", popen_calls[3])
            self.assertIn("huggingface", popen_calls[3])

            # brief via subprocess.run
            self.assertEqual(mock_run.call_count, 1)
            brief_cmd = mock_run.call_args_list[0].args[0]
            self.assertIn("generate_daily_brief.py", brief_cmd[1])

    def test_run_daily_pipeline_parallel_skip_hotspots_no_hf_enrich(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            config_path = self._make_pipeline_config(workdir)

            completed = subprocess.CompletedProcess(args=[], returncode=0)
            popen_calls: list[list[str]] = []

            def fake_popen(cmd: list[str], **_kw: object) -> Mock:
                popen_calls.append(cmd)
                return Mock(wait=Mock(return_value=0), poll=Mock(return_value=0))

            with patch("run_daily_pipeline.subprocess.Popen", side_effect=fake_popen), \
                 patch("run_daily_pipeline.subprocess.run", return_value=completed) as mock_run, \
                 patch(
                     "run_daily_pipeline.sys.argv",
                     [
                         "run_daily_pipeline.py",
                         "--config",
                         str(config_path),
                         "--skip-hotspots",
                     ],
                 ):
                run_daily_pipeline.main()

            # --skip-hotspots: Phase 1 arXiv via run_step (subprocess.run),
            # Phase 2 single arXiv enrich via run_parallel_steps (Popen),
            # Phase 3 brief via run_step (subprocess.run)
            self.assertEqual(len(popen_calls), 1)
            self.assertIn("enrich_summaries.py", popen_calls[0][1])
            self.assertEqual(mock_run.call_count, 2)
            self.assertIn("fetch_arxiv.py", mock_run.call_args_list[0].args[0][1])
            self.assertIn("generate_daily_brief.py", mock_run.call_args_list[1].args[0][1])

    def test_fetch_huggingface_daily_papers_uses_official_api(self) -> None:
        mock_response = Mock()
        mock_response.json.return_value = [{"paper": {"id": "2603.10001", "title": "Reward-Guided Agent Search"}}]
        mock_response.raise_for_status.return_value = None

        with patch("fetch_huggingface.http_get", return_value=mock_response) as mock_get:
            payload = fetch_huggingface.fetch_daily_papers(limit=5, sort="trending", date="2025-03-13")

        self.assertEqual(len(payload), 1)
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[0], fetch_huggingface.HUGGINGFACE_DAILY_PAPERS_API)
        self.assertEqual(mock_get.call_args.kwargs["params"]["limit"], 5)
        self.assertEqual(mock_get.call_args.kwargs["params"]["sort"], "trending")
        self.assertEqual(mock_get.call_args.kwargs["params"]["date"], "2025-03-13")

    def test_collect_hotspots_filters_by_topics_and_builds_note(self) -> None:
        topics = [
            {
                "id": "agents",
                "name": "AI Agents",
                "enabled": True,
                "priority": "high",
                "include_keywords": ["agent", "tool use"],
                "exclude_keywords": [],
                "arxiv_categories": ["cs.AI"],
            }
        ]
        raw_items = [
            {
                "upvotes": 42,
                "numComments": 5,
                "paper": {
                    "id": "2603.10001",
                    "title": "Reward-Guided Agent Search",
                    "summary": "An agent paper about tool use and planning.",
                    "submittedOnDailyAt": "2026-03-13T09:00:00.000Z",
                    "organization": {"fullname": "OpenHF Lab"},
                    "authors": [{"name": "Alice"}],
                    "projectPage": "https://example.com/project",
                },
                "submittedBy": {"fullname": "OpenClaw"},
            },
            {
                "upvotes": 7,
                "numComments": 0,
                "paper": {
                    "id": "2603.10002",
                    "title": "Quantum Chemistry Benchmarks",
                    "summary": "A chemistry benchmark paper.",
                    "submittedOnDailyAt": "2026-03-13T09:00:00.000Z",
                },
            },
        ]

        items = fetch_huggingface.collect_hotspots(raw_items, topics)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["paper_id"], "2603.10001")
        self.assertEqual(items[0]["matched_topics"], ["agents"])
        self.assertIn("Hugging Face 热榜第 1 位", items[0]["note_zh"])
        self.assertIn("AI Agents", items[0]["note_zh"])

    def test_build_arxiv_topic_query_includes_exclude_keywords(self) -> None:
        query = common.build_arxiv_topic_query(
            {
                "include_keywords": ["agent", "tool use"],
                "exclude_keywords": ["game agent", "benchmark"],
                "arxiv_categories": ["cs.AI", "cs.LG"],
            }
        )

        self.assertIn("(all:agent OR all:\"tool use\")", query)
        self.assertIn("(cat:cs.AI OR cat:cs.LG)", query)
        self.assertIn("ANDNOT", query)
        self.assertIn("all:\"game agent\"", query)
        self.assertIn("all:benchmark", query)

    def test_merge_candidates_prefers_stable_ids_over_title(self) -> None:
        merged = common.merge_candidates(
            [
                common.CandidateItem(
                    source="arXiv",
                    title="Tool-Using Multi-Agent Planning",
                    url="https://arxiv.org/abs/2603.00001",
                    paper_id="2603.00001",
                ),
                common.CandidateItem(
                    source="Semantic Scholar",
                    title="Tool Using Multi Agent Planning for Complex Tasks",
                    url="https://api.semanticscholar.org/paper/alpha",
                    paper_id="2603.00001v2",
                ),
                common.CandidateItem(
                    source="arXiv",
                    title="Shared Title",
                    url="https://arxiv.org/abs/2603.00002",
                    paper_id="2603.00002",
                ),
                common.CandidateItem(
                    source="Semantic Scholar",
                    title="Shared Title",
                    url="https://api.semanticscholar.org/paper/beta",
                    paper_id="S2:shared-title",
                ),
            ]
        )

        self.assertEqual(len(merged), 3)
        merged_ids = sorted(item.paper_id for item in merged if item.paper_id)
        self.assertIn("2603.00001", merged_ids)
        self.assertIn("2603.00002", merged_ids)
        self.assertIn("S2:shared-title", merged_ids)

    def test_fetch_arxiv_raises_on_bozo_feed_without_entries(self) -> None:
        broken_feed = SimpleNamespace(
            status=200,
            bozo=1,
            bozo_exception=RuntimeError("temporary network error"),
            entries=[],
        )

        with patch("fetch_arxiv.feedparser.parse", return_value=broken_feed):
            with self.assertRaises(fetch_arxiv.ArxivFeedError):
                fetch_arxiv.fetch("agent", max_results=5)


if __name__ == "__main__":
    unittest.main()
