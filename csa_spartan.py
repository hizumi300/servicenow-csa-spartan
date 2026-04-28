#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / ".csa_spartan"
QUESTIONS_PATH = RUNTIME_DIR / "questions.json"
STATE_PATH = RUNTIME_DIR / "state.json"
CURATED_PATH = RUNTIME_DIR / "curated_600.json"
DOCS_DIR = ROOT / "docs"
WEB_DATA_DIR = DOCS_DIR / "data"
WEB_DATA_PATH = WEB_DATA_DIR / "csa600.json"
DEFAULT_SOURCE = Path.home() / "ServiseNow-CSA-Questions.rtfd" / "TXT.rtf"

HEADING_RE = re.compile(r"^(Question|問題)\s*(\d+)$")
URL_RE = re.compile(r"https?://\S+")
JP_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

QUESTION_STATUS = {
    "Correct": True,
    "Incorrect": False,
    "正解": True,
    "不正解": False,
}

MARKER_TAGS = {
    "Correct answer": {"correct": True, "selected": False},
    "Correct selection": {"correct": True, "selected": False},
    "正解": {"correct": True, "selected": False},
    "正しい選択": {"correct": True, "selected": False},
    "Your answer is correct": {"correct": True, "selected": True},
    "Your selection is correct": {"correct": True, "selected": True},
    "回答は正解です": {"correct": True, "selected": True},
    "選択は正解です": {"correct": True, "selected": True},
    "Your answer is incorrect": {"correct": False, "selected": True},
    "Your selection is incorrect": {"correct": False, "selected": True},
    "回答は不正解です": {"correct": False, "selected": True},
    "選択は不正解です": {"correct": False, "selected": True},
}

OVERALL_LABELS = {"Overall explanation", "全体的な説明"}
DOMAIN_LABELS = {"Domain", "ドメイン"}
EXPLANATION_LABELS = {"Explanation"}
META_PREFIXES = (
    "Learning Domain:",
    "Learning Domain：",
    "学習領域:",
    "学習領域：",
    "Subdomain:",
    "Subdomain：",
    "Additional domain:",
    "Additional domain：",
    "Additional Domains:",
    "Additional Domains：",
    "First introduced:",
    "First introduced：",
    "初回リリース:",
    "初回リリース：",
    "Difficulty level:",
    "Difficulty level：",
    "難易度:",
    "難易度：",
    "Learn more about:",
    "Learn more about：",
    "Learn more here!",
    "Learn more here",
    "Learn more:",
    "Learn more：",
)

TOP_DOMAINS = {
    "platform_overview_navigation": {
        "label": "Platform Overview & Navigation",
        "label_ja": "プラットフォーム概要とナビゲーション",
        "weight": 0.07,
    },
    "instance_configuration": {
        "label": "Instance Configuration",
        "label_ja": "インスタンス構成",
        "weight": 0.10,
    },
    "configuring_applications_for_collaboration": {
        "label": "Configuring Applications for Collaboration",
        "label_ja": "コラボレーション用アプリケーション構成",
        "weight": 0.20,
    },
    "self_service_automation": {
        "label": "Self Service & Automation",
        "label_ja": "セルフサービスと自動化",
        "weight": 0.20,
    },
    "database_management_platform_security": {
        "label": "Database Management & Platform Security",
        "label_ja": "データベース管理とプラットフォームセキュリティ",
        "weight": 0.30,
    },
    "data_migration_integration": {
        "label": "Data Migration & Integration",
        "label_ja": "データ移行と統合",
        "weight": 0.13,
    },
}

DIRECT_DOMAIN_ALIASES = {
    "platform overview & navigation": "platform_overview_navigation",
    "platform overview and navigation": "platform_overview_navigation",
    "platform overview": "platform_overview_navigation",
    "プラットフォーム概要とナビゲーション": "platform_overview_navigation",
    "プラットフォームの概要とナビゲーション": "platform_overview_navigation",
    "プラットフォームの概要とナビゲーション": "platform_overview_navigation",
    "プラットフォムの概要とナビゲション": "platform_overview_navigation",
    "instance configuration": "instance_configuration",
    "インスタンス構成": "instance_configuration",
    "インスタンスの構成": "instance_configuration",
    "configuring applications for collaboration": "configuring_applications_for_collaboration",
    "コラボレーション用アプリケーション構成": "configuring_applications_for_collaboration",
    "コラボレーション用アプリケーションの構成": "configuring_applications_for_collaboration",
    "self service & automation": "self_service_automation",
    "self-service & automation": "self_service_automation",
    "セルフサービスと自動化": "self_service_automation",
    "セルフサービスと自動化": "self_service_automation",
    "database management & platform security": "database_management_platform_security",
    "database management and platform security": "database_management_platform_security",
    "database management": "database_management_platform_security",
    "データベース管理とプラットフォームセキュリティ": "database_management_platform_security",
    "データベース管理とプラットフォームセキュリティ": "database_management_platform_security",
    "データベース管理": "database_management_platform_security",
    "データベース管理": "database_management_platform_security",
    "data migration & integration": "data_migration_integration",
    "data migration and integration": "data_migration_integration",
    "データ移行と統合": "data_migration_integration",
    "データ移行と統合": "data_migration_integration",
}

DOMAIN_KEYWORDS = {
    "platform_overview_navigation": [
        "application navigator",
        "navigator",
        "favorite",
        "favorites",
        "history",
        "breadcrumb",
        "banner",
        "homepage",
        "navigation",
        "platform overview",
        "user menu",
        "search",
        "list view",
        "workspace navigation",
        "platform capabilities",
        "global search",
        "platform",
        "ナビゲーション",
        "お気に入り",
        "履歴",
        "ユーザーメニュー",
        "検索",
        "ホームページ",
        "アプリケーションナビゲータ",
        "プラットフォームの概要",
    ],
    "instance_configuration": [
        "instance",
        "plugin",
        "plugins",
        "property",
        "properties",
        "system property",
        "form layout",
        "form designer",
        "form builder",
        "field",
        "fields",
        "dictionary",
        "choice list",
        "client script",
        "ui policy",
        "ui action",
        "data policy",
        "table builder",
        "common user interfaces",
        "notification preferences",
        "instance configuration",
        "plugin activation",
        "system properties",
        "フォームビルダー",
        "フォームデザイナー",
        "フィールド",
        "テーブル",
        "辞書",
        "選択肢リスト",
        "ui policy",
        "ui action",
        "client script",
        "data policy",
        "プラグイン",
        "システムプロパティ",
        "インスタンス",
    ],
    "configuring_applications_for_collaboration": [
        "notification",
        "notifications",
        "email",
        "knowledge",
        "report",
        "reports",
        "dashboard",
        "dashboards",
        "performance analytics",
        "platform analytics",
        "visual task board",
        "vtb",
        "survey",
        "workspace email",
        "notification settings",
        "knowledge base",
        "reporting",
        "notifications",
        "通知",
        "メール",
        "ナレッジ",
        "レポート",
        "ダッシュボード",
        "performance analytics",
        "platform analytics",
        "visual task boards",
        "可視化",
        "ビジュアルタスクボード",
        "workspace",
    ],
    "self_service_automation": [
        "service catalog",
        "catalog item",
        "catalog",
        "order guide",
        "record producer",
        "virtual agent",
        "flow designer",
        "workflow studio",
        "workflow",
        "subflow",
        "playbook",
        "decision builder",
        "approval",
        "automation",
        "service portal",
        "request item",
        "self-service",
        "record producers",
        "automation engine",
        "サービスカタログ",
        "カタログ",
        "オーダーガイド",
        "レコードプロデューサー",
        "virtual agent",
        "仮想エージェント",
        "flow designer",
        "workflow studio",
        "playbook",
        "automation",
        "セルフサービス",
        "サービスポータル",
    ],
    "database_management_platform_security": [
        "cmdb",
        "csdm",
        "access control",
        "acl",
        "security",
        "role",
        "roles",
        "user criteria",
        "schema",
        "table",
        "task table",
        "configuration item",
        "ci ",
        "database",
        "data schema",
        "dictionary override",
        "secured",
        "cmdb data manager",
        "dependent ci",
        "ユーザー基準",
        "アクセス制御",
        "acl",
        "セキュリティ",
        "ロール",
        "cmdb",
        "csdm",
        "データスキーマ",
        "構成アイテム",
        "ci",
        "テーブル",
        "データベース",
    ],
    "data_migration_integration": [
        "import",
        "import set",
        "transform map",
        "transform",
        "coalesce",
        "data source",
        "integration",
        "integration hub",
        "ldap",
        "jdbc",
        "rest",
        "soap",
        "web service",
        "xml",
        "csv",
        "excel",
        "migration",
        "etl",
        "データ移行",
        "統合",
        "インポート",
        "インポートセット",
        "変換マップ",
        "transform map",
        "coalesce",
        "integration hub",
        "data source",
        "rest",
        "soap",
        "ldap",
    ],
}

GLOSSARY = {
    "Access Control Rules": "アクセス制御ルール",
    "Access Control Rule": "アクセス制御ルール",
    "Application Navigator": "アプリケーションナビゲータ",
    "Asset Contracts": "資産契約",
    "Business Rule": "ビジネスルール",
    "Catalog Item": "カタログアイテム",
    "Catalog Items": "カタログアイテム",
    "Change Request": "変更要求",
    "Client Script": "クライアントスクリプト",
    "CMDB Data Manager": "CMDBデータマネージャ",
    "CMDB": "CMDB",
    "Common Service Data Model": "共通サービスデータモデル",
    "Configuration Item": "構成アイテム",
    "Configuration Items": "構成アイテム",
    "Data Policy": "データポリシー",
    "Data Policies": "データポリシー",
    "Data Source": "データソース",
    "Data Sources": "データソース",
    "Dashboard": "ダッシュボード",
    "Dashboards": "ダッシュボード",
    "Dictionary Override": "辞書オーバーライド",
    "Email": "メール",
    "Favorites": "お気に入り",
    "Favorite": "お気に入り",
    "Field": "フィールド",
    "Fields": "フィールド",
    "Flow Designer": "Flow Designer",
    "Form Builder": "フォームビルダー",
    "Form Design": "フォーム設計",
    "Form Designer": "フォームデザイナー",
    "Global Search": "グローバル検索",
    "Homepages": "ホームページ",
    "Homepage": "ホームページ",
    "Import Set": "インポートセット",
    "Import Sets": "インポートセット",
    "Integration Hub": "Integration Hub",
    "Knowledge Base": "ナレッジベース",
    "Knowledge": "ナレッジ",
    "List": "リスト",
    "Lists": "リスト",
    "Module": "モジュール",
    "Modules": "モジュール",
    "Notifications": "通知",
    "Notification": "通知",
    "Order Guide": "オーダーガイド",
    "Order Guides": "オーダーガイド",
    "Performance Analytics": "Performance Analytics",
    "Platform Analytics": "Platform Analytics",
    "Plugin": "プラグイン",
    "Plugins": "プラグイン",
    "Record Producer": "レコードプロデューサー",
    "Record Producers": "レコードプロデューサー",
    "Report": "レポート",
    "Reports": "レポート",
    "Request Item": "依頼アイテム",
    "Role": "ロール",
    "Roles": "ロール",
    "Schema": "スキーマ",
    "Service Catalog": "サービスカタログ",
    "Service Portal": "Service Portal",
    "Task Surveys": "タスク調査",
    "Task table": "Taskテーブル",
    "Transform Map": "変換マップ",
    "Transform Maps": "変換マップ",
    "UI Action": "UI Action",
    "UI Actions": "UI Action",
    "UI Policy": "UI Policy",
    "UI Policies": "UI Policy",
    "User menu": "ユーザーメニュー",
    "User Menu": "ユーザーメニュー",
    "Variable": "変数",
    "Variable Set": "変数セット",
    "Variables": "変数",
    "View / Run": "View / Run",
    "Virtual Agent": "Virtual Agent",
    "Visual Task Board": "ビジュアルタスクボード",
    "Visual Task Boards": "ビジュアルタスクボード",
    "Workflow Studio": "Workflow Studio",
}

DOC_TOPIC_HINTS = [
    ("access control", "Access control rules"),
    ("acl", "Access control rules"),
    ("cmdb data manager", "CMDB Data Manager"),
    ("cmdb", "CMDB"),
    ("csdm", "Common Service Data Model"),
    ("service catalog", "Service Catalog"),
    ("record producer", "Record Producers"),
    ("order guide", "Order Guides"),
    ("flow designer", "Flow Designer"),
    ("workflow studio", "Workflow Studio"),
    ("virtual agent", "Virtual Agent"),
    ("notification", "Notifications"),
    ("knowledge", "Knowledge Management"),
    ("visual task board", "Visual Task Boards"),
    ("dashboard", "Dashboards"),
    ("performance analytics", "Performance Analytics"),
    ("import set", "Import Sets"),
    ("transform map", "Transform Maps"),
    ("coalesce", "Coalesce"),
    ("data source", "Data Sources"),
    ("ui policy", "UI policies"),
    ("ui action", "UI actions"),
    ("client script", "Client scripts"),
    ("data policy", "Data policies"),
    ("choice list", "Choice lists"),
    ("フォームビルダー", "Form Builder"),
    ("通知", "Notifications"),
    ("ナレッジ", "Knowledge Management"),
    ("サービスカタログ", "Service Catalog"),
    ("仮想エージェント", "Virtual Agent"),
    ("ビジュアルタスクボード", "Visual Task Boards"),
    ("ダッシュボード", "Dashboards"),
    ("performance analytics", "Performance Analytics"),
    ("インポートセット", "Import Sets"),
    ("変換マップ", "Transform Maps"),
]

CURATED_BANK_SIZE = 600
DEFAULT_STUDY_DAYS = 14
DEFAULT_DAILY_HOURS = 2.5

CURATION_TOPIC_TAGS = {
    "platform_overview_navigation": {
        "navigator": ["application navigator", "navigator", "ナビゲータ"],
        "favorites": ["favorite", "favorites", "お気に入り", "favorite"],
        "history": ["history", "履歴"],
        "search": ["global search", "search", "検索"],
        "lists_filters": ["list", "lists", "filter", "filters", "リスト", "フィルター"],
        "user_menu": ["user menu", "ユーザーメニュー", "impersonate", "elevate roles"],
        "forms": ["form", "forms", "フォーム"],
    },
    "instance_configuration": {
        "form_builder": ["form builder", "フォームビルダー"],
        "form_designer": ["form designer", "フォームデザイナー"],
        "client_scripts": ["client script", "client scripts", "クライアントスクリプト"],
        "ui_policies": ["ui policy", "ui policies", "uiポリシー"],
        "ui_actions": ["ui action", "ui actions", "関連リンク", "context menu", "コンテキストメニュー"],
        "data_policies": ["data policy", "data policies", "データポリシー"],
        "dictionary": ["dictionary", "辞書", "choice list", "選択肢リスト"],
        "properties_plugins": ["system property", "properties", "plugin", "plugins", "システムプロパティ", "プラグイン"],
    },
    "configuring_applications_for_collaboration": {
        "notifications": ["notification", "notifications", "通知", "email", "メール"],
        "knowledge": ["knowledge", "knowledge base", "ナレッジ"],
        "reports": ["report", "reports", "レポート", "metric", "metrics"],
        "dashboards": ["dashboard", "dashboards", "ダッシュボード"],
        "analytics": ["performance analytics", "platform analytics", "analytics"],
        "task_boards": ["visual task board", "visual task boards", "vtb", "ビジュアルタスクボード"],
    },
    "self_service_automation": {
        "service_catalog": ["service catalog", "catalog item", "サービスカタログ", "カタログアイテム"],
        "order_guides": ["order guide", "order guides", "オーダーガイド"],
        "record_producers": ["record producer", "record producers", "レコードプロデューサー"],
        "virtual_agent": ["virtual agent", "仮想エージェント"],
        "flow_designer": ["flow designer", "subflow", "action designer"],
        "workflow": ["workflow studio", "workflow", "approval", "request item", "サービスポータル", "service portal"],
    },
    "database_management_platform_security": {
        "access_control": ["access control", "acl", "アクセス制御", "acl"],
        "security_roles": ["role", "roles", "security", "user criteria", "ロール", "セキュリティ", "ユーザー基準"],
        "schema_tables": ["schema", "table", "tables", "スキーマ", "テーブル"],
        "cmdb_csdm": ["cmdb", "csdm", "構成アイテム", "configuration item", "configuration items"],
        "task_table": ["task table", "task [task]", "taskテーブル"],
        "dictionary_override": ["dictionary override", "辞書オーバーライド"],
    },
    "data_migration_integration": {
        "import_sets": ["import set", "import sets", "インポートセット"],
        "transform_maps": ["transform map", "transform maps", "変換マップ"],
        "coalesce": ["coalesce"],
        "data_sources": ["data source", "data sources", "データソース"],
        "integration": ["integration", "integration hub", "rest", "soap", "ldap", "統合"],
    },
}

NARROW_SCOPE_PATTERNS = [
    "compatibility mode",
    "embedded content",
    "iframe",
    "migration center",
    "decision builder",
    "playbook",
    "workspace email",
    "auto-save",
    "cascade-cleanup",
    "orphan-dependent",
    "cleanup orphan cis",
]

OFFICIAL_EXAM_CONTEXT = {
    "as_of_date": "2026-04-28",
    "exam_blueprint_updated": "2026-01",
    "current_release_family": "Australia",
    "current_release_updated": "2026-04-03",
    "sources": [
        "https://nowlearning.servicenow.com/kb?id=kb_article_view&sysparm_article=KB0011554",
        "https://www.servicenow.com/docs/r/release-notes/available-versions.html",
        "https://www.servicenow.com/docs/r/release-notes/core-platform-rn.html",
    ],
    "exam_priority_topics": [
        "next_experience_unified_navigation",
        "platform_analytics",
        "workflow_studio",
        "virtual_agent",
        "security_center",
        "shared_responsibility_model",
    ],
}

ADAPTIVE_CONCEPT_TAGS = {
    "platform_overview_navigation": {
        "platform_overview": ["platform overview", "platform capabilities", "servicenow platform overview", "プラットフォームの概要"],
        "the_instance": ["the servicenow instance", "instance", "インスタンス"],
        "next_experience_unified_navigation": ["next experience", "unified navigation", "application navigator", "favorite", "favorites", "history", "breadcrumb", "お気に入り", "履歴", "ナビゲーション"],
        "search_and_lists": ["search", "global search", "list", "lists", "filter", "filters", "tag", "tags", "検索", "リスト", "フィルター", "タグ"],
        "user_menu_and_roles": ["user menu", "impersonate", "elevate roles", "ユーザーメニュー", "権限昇格"],
    },
    "instance_configuration": {
        "installing_applications_and_plugins": ["installing applications", "plugin", "plugins", "application", "applications", "プラグイン", "アプリケーション"],
        "personalizing_customizing_instance": ["personalize", "personalizing", "customizing", "customize", "branding", "テーマ", "personalizing/customizing"],
        "common_user_interfaces": ["form builder", "form designer", "common user interfaces", "workspace", "choice list", "フォームビルダー", "フォームデザイナー", "共通ユーザーインターフェース"],
        "instance_properties": ["system property", "system properties", "property", "properties", "システムプロパティ"],
    },
    "configuring_applications_for_collaboration": {
        "lists_filters_tags": ["lists", "list", "filter", "filters", "tags", "リスト", "フィルター", "タグ"],
        "list_and_form_anatomy": ["form anatomy", "list and form", "related list", "フォーム", "リスト"],
        "form_configuration": ["form configuration", "form templates", "form layout", "advanced form configuration", "フォーム設定", "フォームテンプレート"],
        "task_management": ["task management", "task", "assignment", "fulfillment", "タスク管理"],
        "visual_task_boards": ["visual task board", "visual task boards", "vtb", "ビジュアルタスクボード"],
        "platform_analytics": ["platform analytics", "performance analytics", "dashboard", "report", "reports", "visualizations", "ダッシュボード", "レポート", "可視化"],
        "notifications": ["notification", "notifications", "email", "メール", "通知"],
    },
    "self_service_automation": {
        "knowledge_management": ["knowledge", "knowledge base", "permalink", "ナレッジ", "ナレッジベース"],
        "service_catalog": ["service catalog", "catalog item", "record producer", "order guide", "request item", "サービスカタログ", "カタログアイテム", "レコードプロデューサー", "オーダーガイド"],
        "workflow_studio": ["workflow studio", "workflow", "decision builder", "playbook", "workflow authoring"],
        "virtual_agent": ["virtual agent", "topic", "nlu", "chat", "仮想エージェント"],
    },
    "database_management_platform_security": {
        "data_schema": ["data schema", "schema", "dictionary", "table", "field", "data model", "スキーマ", "辞書", "テーブル", "フィールド"],
        "application_access_control": ["access control", "acl", "role", "roles", "user criteria", "アクセス制御", "ロール", "ユーザー基準"],
        "importing_data": ["importing data", "import", "import set", "transform map", "coalesce", "インポート", "インポートセット", "変換マップ"],
        "cmdb_and_csdm": ["cmdb", "csdm", "configuration item", "構成アイテム"],
        "security_center": ["security center"],
        "shared_responsibility_model": ["shared responsibility model", "責任共有モデル"],
    },
    "data_migration_integration": {
        "ui_policies": ["ui policy", "ui policies", "uiポリシー"],
        "business_rules": ["business rule", "business rules", "ビジネスルール"],
        "system_update_sets": ["system update set", "system update sets", "update set", "更新セット"],
        "scripting_in_servicenow": ["scripting", "javascript", "client script", "server script", "script", "スクリプト", "javascript"],
    },
}

CURRENT_RELEASE_PRIORITY_TAGS = {
    "next_experience_unified_navigation",
    "platform_analytics",
    "workflow_studio",
    "virtual_agent",
    "security_center",
    "shared_responsibility_model",
}


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.replace("\xa0", " "))
    return text.strip()


def normalize_key(text: str) -> str:
    text = normalize_text(text).lower()
    return re.sub(r"\s+", " ", text)


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)


def extract_text(source: Path) -> str:
    try:
        return subprocess.check_output(
            ["textutil", "-convert", "txt", "-stdout", str(source)],
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"RTFの抽出に失敗: {exc}") from exc


def split_paragraphs(lines: List[str]) -> List[List[str]]:
    paragraphs: List[List[str]] = []
    current: List[str] = []
    for raw in lines:
        line = normalize_text(raw)
        if not line:
            if current:
                paragraphs.append(current)
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(current)
    return paragraphs


def is_meta_start(line: str) -> bool:
    if line in OVERALL_LABELS or line in DOMAIN_LABELS:
        return True
    if line.startswith("Learn more") or line.startswith("学習領域") or line.startswith("Learning Domain"):
        return True
    if line.startswith("Subdomain") or line.startswith("Additional domain") or line.startswith("Additional Domains"):
        return True
    if line.startswith("First introduced") or line.startswith("初回リリース"):
        return True
    if line.startswith("Difficulty level") or line.startswith("難易度"):
        return True
    if line in {"リソース", "Resources", "Resource"}:
        return True
    if is_screenshot_label(line):
        return True
    if URL_RE.search(line):
        return True
    return False


def is_screenshot_label(line: str) -> bool:
    normalized = normalize_text(line)
    return bool(
        re.match(r"^スクリーンショット(?:\s*\d+)?[：:]", normalized)
        or re.match(r"^画面録画(?:\s*\d+)?[：:]", normalized)
        or re.match(r"^Screenshot(?:\s*\d+)?[：:]", normalized, flags=re.IGNORECASE)
        or re.match(r"^Screen recording(?:\s*\d+)?[：:]", normalized, flags=re.IGNORECASE)
    )


def split_headings(text: str) -> List[Dict[str, object]]:
    lines = text.splitlines()
    headings: List[Tuple[int, str, int]] = []
    for idx, raw in enumerate(lines):
        match = HEADING_RE.match(normalize_text(raw))
        if match:
            headings.append((idx, match.group(1), int(match.group(2))))
    segments: List[Tuple[int, int]] = []
    seg_start = 0
    for idx in range(1, len(headings)):
        if headings[idx][2] <= headings[idx - 1][2]:
            segments.append((seg_start, idx))
            seg_start = idx
    if headings:
        segments.append((seg_start, len(headings)))

    blocks: List[Dict[str, object]] = []
    for set_index, (start_idx, end_idx) in enumerate(segments, start=1):
        for local_index in range(start_idx, end_idx):
            line_index, style, number = headings[local_index]
            next_line_index = headings[local_index + 1][0] if local_index + 1 < len(headings) else len(lines)
            block_lines = [normalize_text(line) for line in lines[line_index:next_line_index]]
            blocks.append(
                {
                    "set_index": set_index,
                    "style": style,
                    "number": number,
                    "lines": block_lines,
                }
            )
    return blocks


def make_question_id(global_index: int) -> str:
    return f"CSA-{global_index:04d}"


def pick_prompt_language(text: str) -> str:
    return "ja" if JP_CHAR_RE.search(text) else "en"


def score_pending_markers(markers: List[str]) -> Dict[str, bool]:
    merged = {"correct": False, "selected": False}
    for marker in markers:
        tags = MARKER_TAGS.get(marker, {})
        if tags.get("correct"):
            merged["correct"] = True
        if tags.get("selected"):
            merged["selected"] = True
    return merged


def clean_marker_lines(lines: List[str]) -> Tuple[List[str], List[str], List[str]]:
    working = list(lines)
    leading: List[str] = []
    trailing: List[str] = []
    while working and working[0] in MARKER_TAGS:
        leading.append(working.pop(0))
    while working and working[-1] in MARKER_TAGS:
        trailing.insert(0, working.pop())
    return leading, working, trailing


def parse_meta_lines(lines: List[str], meta: Dict[str, object]) -> None:
    current_section: Optional[str] = None
    for raw in lines:
        line = normalize_text(raw)
        if not line:
            continue
        urls = URL_RE.findall(line)
        if urls:
            existing = meta.setdefault("doc_urls", [])
            for url in urls:
                if url not in existing:
                    existing.append(url)
            continue
        if line in OVERALL_LABELS:
            current_section = "overall"
            continue
        if line in DOMAIN_LABELS:
            current_section = "domain"
            continue
        if line in {"リソース", "Resources", "Resource"}:
            current_section = None
            continue
        if is_screenshot_label(line):
            current_section = None
            continue
        if line.startswith("Learn more about:") or line.startswith("Learn more about："):
            current_section = "learn_more"
            continue
        if line.startswith("Learn more here"):
            current_section = None
            continue
        if line.startswith("Learning Domain:") or line.startswith("Learning Domain："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta.setdefault("learning_domains", []).append(value.strip())
            current_section = None
            continue
        if line.startswith("学習領域:") or line.startswith("学習領域："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta.setdefault("learning_domains", []).append(value.strip())
            current_section = None
            continue
        if line.startswith("Subdomain:") or line.startswith("Subdomain："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta.setdefault("subdomains", []).append(value.strip())
            current_section = None
            continue
        if line.startswith("Additional domain:") or line.startswith("Additional domain："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta.setdefault("additional_domains", []).append(value.strip())
            current_section = None
            continue
        if line.startswith("Additional Domains:") or line.startswith("Additional Domains："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta.setdefault("additional_domains", []).append(value.strip())
            current_section = None
            continue
        if line.startswith("First introduced:") or line.startswith("First introduced："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta["first_introduced"] = value.strip()
            current_section = None
            continue
        if line.startswith("初回リリース:") or line.startswith("初回リリース："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta["first_introduced"] = value.strip()
            current_section = None
            continue
        if line.startswith("Difficulty level:") or line.startswith("Difficulty level："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta["difficulty"] = value.strip()
            current_section = None
            continue
        if line.startswith("難易度:") or line.startswith("難易度："):
            value = line.split(":", 1)[1] if ":" in line else line.split("：", 1)[1]
            meta["difficulty"] = value.strip()
            current_section = None
            continue
        if current_section == "overall":
            meta.setdefault("overall_explanation_lines", []).append(line)
            continue
        if current_section == "domain":
            meta.setdefault("domain_labels", []).append(line)
            continue
        if current_section == "learn_more":
            meta.setdefault("learn_more_topics", []).append(line.lstrip("•").strip())
            continue


def parse_option_paragraph(lines: List[str], pending_markers: List[str]) -> Tuple[Optional[Dict[str, object]], List[str], List[str]]:
    leading, working, trailing = clean_marker_lines(lines)
    tags = list(pending_markers) + leading

    meta_index = next((idx for idx, line in enumerate(working) if is_meta_start(line)), None)
    post_meta: List[str] = []
    if meta_index is not None:
        post_meta = working[meta_index:]
        working = working[:meta_index]

    if not working:
        return None, trailing, post_meta

    if "Explanation" in working:
        exp_idx = working.index("Explanation")
        choice_lines = working[:exp_idx]
        explanation_lines = working[exp_idx + 1 :]
    else:
        choice_lines = working
        explanation_lines = []

    choice_text = " ".join(choice_lines).strip()
    if not choice_text:
        return None, trailing, post_meta

    merged_tags = score_pending_markers(tags)
    option = {
        "text": choice_text,
        "explanation": " ".join(explanation_lines).strip(),
        "is_correct": bool(merged_tags["correct"]),
        "was_selected": bool(merged_tags["selected"]),
    }
    return option, trailing, post_meta


def infer_overall_explanation(options: List[Dict[str, object]]) -> str:
    fragments = [opt["explanation"] for opt in options if opt.get("is_correct") and opt.get("explanation")]
    if fragments:
        return " ".join(fragments)
    fragments = [opt["explanation"] for opt in options if opt.get("explanation")]
    return fragments[0] if fragments else ""


def prompt_choose_count(prompt: str) -> int:
    lowered = normalize_key(prompt)
    patterns = {
        2: ["choose two", "2つ選択", "2 つ選択"],
        3: ["choose three", "3つ選択", "3 つ選択"],
        4: ["choose four", "4つ選択", "4 つ選択"],
    }
    for count, variants in patterns.items():
        if any(variant in lowered for variant in variants):
            return count
    return 1


def canonical_signature(prompt: str, choices: Iterable[str]) -> str:
    joined = normalize_key(prompt) + "||" + "||".join(normalize_key(choice) for choice in choices)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def translate_text_en(text: str) -> str:
    if not text:
        return text
    translated = normalize_text(text)

    replacements = [
        (r"\(Choose two\.\)", "（2つ選択）"),
        (r"\(Choose three\.\)", "（3つ選択）"),
        (r"\(Choose four\.\)", "（4つ選択）"),
        (r"\(Choose all that apply\.\)", "（該当するものをすべて選択）"),
    ]
    for pattern, value in replacements:
        translated = re.sub(pattern, value, translated, flags=re.IGNORECASE)

    for source, target in sorted(GLOSSARY.items(), key=lambda item: len(item[0]), reverse=True):
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)

    if translated.lower().startswith("which one of the following"):
        translated = re.sub(r"(?i)^which one of the following\s+", "次のうち、", translated)
        translated = re.sub(r"\?$", " はどれですか？", translated)
    elif translated.lower().startswith("which of the following"):
        translated = re.sub(r"(?i)^which of the following\s+", "次のうち、", translated)
        translated = re.sub(r"\?$", " はどれですか？", translated)
    elif translated.lower().startswith("which term refers to"):
        translated = re.sub(r"(?i)^which term refers to\s+", "", translated)
        translated = translated.rstrip("?")
        translated = f"どの用語が {translated} を指しますか？"
    elif translated.lower().startswith("what is generated from"):
        translated = re.sub(r"(?i)^what is generated from\s+", "", translated)
        translated = translated.rstrip("?")
        translated = f"{translated} から生成されるものはどれですか？"
    elif translated.lower().startswith("what module do you use to"):
        translated = re.sub(r"(?i)^what module do you use to\s+", "", translated)
        translated = translated.rstrip("?")
        translated = f"{translated} するにはどのモジュールを使用しますか？"
    elif translated.lower().startswith("what are the"):
        translated = re.sub(r"(?i)^what are the\s+", "", translated)
        translated = translated.rstrip("?")
        translated = f"{translated} は何ですか？"
    elif translated.lower().startswith("what is the"):
        translated = re.sub(r"(?i)^what is the\s+", "", translated)
        translated = translated.rstrip("?")
        translated = f"{translated} は何ですか？"
    elif translated.lower().startswith("how many"):
        translated = re.sub(r"(?i)^how many\s+", "", translated)
        translated = translated.rstrip("?")
        translated = f"{translated} はいくつですか？"

    translated = translated.replace(" ,", "、").replace(", ", "、")
    translated = translated.replace(" ? ", "？ ").replace(" ?", "？")
    return translated


def docs_search_url(topic: str) -> str:
    return f"https://www.servicenow.com/docs/search?q={quote_plus(topic)}"


def top_domain_from_alias(raw_value: str) -> Optional[str]:
    key = normalize_key(raw_value)
    if key in DIRECT_DOMAIN_ALIASES:
        return DIRECT_DOMAIN_ALIASES[key]

    keyword_aliases = [
        ("service catalog", "self_service_automation"),
        ("virtual agent", "self_service_automation"),
        ("workflow studio", "self_service_automation"),
        ("flow designer", "self_service_automation"),
        ("playbook", "self_service_automation"),
        ("automation", "self_service_automation"),
        ("通知", "configuring_applications_for_collaboration"),
        ("notification", "configuring_applications_for_collaboration"),
        ("knowledge", "configuring_applications_for_collaboration"),
        ("report", "configuring_applications_for_collaboration"),
        ("dashboard", "configuring_applications_for_collaboration"),
        ("performance analytics", "configuring_applications_for_collaboration"),
        ("visual task board", "configuring_applications_for_collaboration"),
        ("platform analytics", "configuring_applications_for_collaboration"),
        ("cmdb", "database_management_platform_security"),
        ("csdm", "database_management_platform_security"),
        ("security", "database_management_platform_security"),
        ("access control", "database_management_platform_security"),
        ("acl", "database_management_platform_security"),
        ("schema", "database_management_platform_security"),
        ("data schema", "database_management_platform_security"),
        ("import", "data_migration_integration"),
        ("transform map", "data_migration_integration"),
        ("integration", "data_migration_integration"),
        ("coalesce", "data_migration_integration"),
        ("ナビゲーション", "platform_overview_navigation"),
        ("お気に入り", "platform_overview_navigation"),
        ("検索", "platform_overview_navigation"),
        ("フォーム", "instance_configuration"),
        ("ui policy", "instance_configuration"),
        ("ui action", "instance_configuration"),
        ("data policy", "instance_configuration"),
        ("table", "database_management_platform_security"),
    ]
    for needle, domain_key in keyword_aliases:
        if needle in key:
            return domain_key
    return None


def classify_domain(question: Dict[str, object]) -> Tuple[str, float, str]:
    metadata_candidates: List[str] = []
    metadata_candidates.extend(question.get("learning_domains", []))
    metadata_candidates.extend(question.get("additional_domains", []))
    metadata_candidates.extend(question.get("subdomains", []))
    metadata_candidates.extend(question.get("domain_labels", []))

    for value in metadata_candidates:
        domain_key = top_domain_from_alias(value)
        if domain_key:
            return domain_key, 1.0, f"metadata:{value}"

    corpus_parts = [question["prompt"]]
    corpus_parts.extend(choice["text"] for choice in question["choices"])
    corpus_parts.extend(metadata_candidates)
    corpus = normalize_key(" ".join(part for part in corpus_parts if part))

    scores = {key: 0.0 for key in TOP_DOMAINS}
    for domain_key, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in corpus:
                scores[domain_key] += 1.0 + (0.4 if " " in keyword else 0.0)

    if not any(scores.values()):
        return "database_management_platform_security", 0.2, "fallback:no-match"

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    winner, winner_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = 0.45 if winner_score <= 1.0 else 0.65
    if winner_score >= runner_up + 1.5:
        confidence = min(0.85, confidence + 0.15)
    return winner, confidence, "keyword"


def parse_question_block(block: Dict[str, object], global_index: int) -> Dict[str, object]:
    lines = [line for line in block["lines"] if line is not None]
    paragraphs = split_paragraphs(lines)
    if not paragraphs:
        raise ValueError(f"Empty block at {global_index}")

    head = list(paragraphs[0])
    heading = head.pop(0)
    status = None
    if head and head[0] in QUESTION_STATUS:
        status = QUESTION_STATUS[head.pop(0)]

    pending_markers: List[str] = []
    while head and head[-1] in MARKER_TAGS:
        pending_markers.insert(0, head.pop())
    prompt = " ".join(head).strip()
    language = pick_prompt_language(prompt)

    choices: List[Dict[str, object]] = []
    meta: Dict[str, object] = {}
    in_meta = False

    for paragraph in paragraphs[1:]:
        if in_meta or (paragraph and is_meta_start(paragraph[0])):
            in_meta = True
            parse_meta_lines(paragraph, meta)
            continue

        option, pending_markers, post_meta = parse_option_paragraph(paragraph, pending_markers)
        if option:
            choices.append(option)
        if post_meta:
            in_meta = True
            parse_meta_lines(post_meta, meta)

    for idx, choice in enumerate(choices):
        choice["id"] = chr(ord("A") + idx)
        if language == "en":
            choice["text_ja"] = translate_text_en(choice["text"])
        else:
            choice["text_ja"] = choice["text"]

    overall_explanation = " ".join(meta.get("overall_explanation_lines", [])).strip()
    if not overall_explanation:
        overall_explanation = infer_overall_explanation(choices)

    correct_ids = [choice["id"] for choice in choices if choice.get("is_correct")]
    selected_ids = [choice["id"] for choice in choices if choice.get("was_selected")]
    choose_count = prompt_choose_count(prompt)
    if len(correct_ids) > choose_count:
        choose_count = len(correct_ids)
    multi_select = choose_count > 1 or len(correct_ids) > 1

    question = {
        "id": make_question_id(global_index),
        "global_index": global_index,
        "source_set": block["set_index"],
        "source_number": block["number"],
        "source_style": block["style"],
        "source_heading": heading,
        "source_status_correct": status,
        "prompt": prompt,
        "prompt_ja": prompt if language == "ja" else translate_text_en(prompt),
        "language": language,
        "multi_select": multi_select,
        "choose_count": choose_count,
        "choices": choices,
        "correct_choice_ids": correct_ids,
        "selected_choice_ids": selected_ids,
        "overall_explanation": overall_explanation,
        "overall_explanation_ja": overall_explanation if language == "ja" else translate_text_en(overall_explanation),
        "learning_domains": meta.get("learning_domains", []),
        "domain_labels": meta.get("domain_labels", []),
        "subdomains": meta.get("subdomains", []),
        "additional_domains": meta.get("additional_domains", []),
        "first_introduced": meta.get("first_introduced"),
        "difficulty": meta.get("difficulty"),
        "learn_more_topics": meta.get("learn_more_topics", []),
        "doc_urls": meta.get("doc_urls", []),
    }
    question["signature"] = canonical_signature(question["prompt"], [choice["text"] for choice in choices])
    domain_key, confidence, source = classify_domain(question)
    question["top_domain"] = domain_key
    question["top_domain_confidence"] = confidence
    question["domain_source"] = source
    return question


def build_dataset(source: Path, force: bool = False) -> Dict[str, object]:
    ensure_runtime_dir()
    if QUESTIONS_PATH.exists() and not force:
        return load_questions()

    raw_text = extract_text(source)
    blocks = split_headings(raw_text)
    questions: List[Dict[str, object]] = []
    for index, block in enumerate(blocks, start=1):
        try:
            questions.append(parse_question_block(block, index))
        except Exception as exc:  # pragma: no cover - resilience over purity
            questions.append(
                {
                    "id": make_question_id(index),
                    "global_index": index,
                    "source_set": block["set_index"],
                    "source_number": block["number"],
                    "source_style": block["style"],
                    "source_heading": f"{block['style']} {block['number']}",
                    "source_status_correct": None,
                    "prompt": f"[parse error] {exc}",
                    "prompt_ja": f"[parse error] {exc}",
                    "language": "ja",
                    "multi_select": False,
                    "choose_count": 1,
                    "choices": [],
                    "correct_choice_ids": [],
                    "selected_choice_ids": [],
                    "overall_explanation": "",
                    "overall_explanation_ja": "",
                    "learning_domains": [],
                    "domain_labels": [],
                    "subdomains": [],
                    "additional_domains": [],
                    "first_introduced": None,
                    "difficulty": None,
                    "learn_more_topics": [],
                    "doc_urls": [],
                    "signature": "",
                    "top_domain": "database_management_platform_security",
                    "top_domain_confidence": 0.0,
                    "domain_source": f"parse_error:{exc}",
                }
            )

    signature_counts: Dict[str, int] = {}
    for question in questions:
        signature_counts[question["signature"]] = signature_counts.get(question["signature"], 0) + 1
    for question in questions:
        question["duplicate_count"] = signature_counts.get(question["signature"], 1)

    payload = {
        "built_at": iso_now(),
        "source": str(source),
        "question_count": len(questions),
        "questions": questions,
    }
    QUESTIONS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_questions() -> Dict[str, object]:
    if not QUESTIONS_PATH.exists():
        raise SystemExit("先に `python3 csa_spartan.py build` を実行してください。")
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def load_state() -> Dict[str, object]:
    if not STATE_PATH.exists():
        return {"version": 1, "attempts": {}, "sessions": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: Dict[str, object]) -> None:
    ensure_runtime_dir()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def answer_tokens(value: str) -> List[str]:
    tokens = [token.strip().upper() for token in re.split(r"[,\s/]+", value) if token.strip()]
    return sorted(dict.fromkeys(tokens))


def question_seed_stats(question: Dict[str, object]) -> Tuple[int, int]:
    if question.get("source_status_correct") is True:
        return 1, 1
    if question.get("source_status_correct") is False:
        return 0, 1
    return 0, 0


def attempt_snapshot(question: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    attempts = state.get("attempts", {})
    record = attempts.get(question["id"], {})
    seed_correct, seed_total = question_seed_stats(question)
    total = seed_total + int(record.get("total", 0))
    correct = seed_correct + int(record.get("correct", 0))
    accuracy = (correct / total) if total else 0.0
    due_at = record.get("due_at")
    return {
        "record": record,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "due_at": due_at,
        "streak": int(record.get("streak", 0)),
    }


def spaced_repetition_due(correct: bool, streak: int) -> datetime:
    base = now_local()
    if not correct:
        return base + timedelta(minutes=15)
    intervals = {
        1: timedelta(hours=12),
        2: timedelta(days=1),
        3: timedelta(days=3),
        4: timedelta(days=7),
    }
    return base + intervals.get(streak, timedelta(days=14))


def priority_score(question: Dict[str, object], state: Dict[str, object]) -> float:
    snapshot = attempt_snapshot(question, state)
    score = 50.0
    if question.get("source_status_correct") is False:
        score += 18.0
    if question.get("duplicate_count", 1) > 1:
        score -= 3.0
    if question.get("multi_select"):
        score += 4.0

    score += (1.0 - snapshot["accuracy"]) * 28.0
    score -= min(snapshot["streak"] * 3.0, 12.0)

    due_at_raw = snapshot["due_at"]
    if due_at_raw:
        due_at = datetime.fromisoformat(due_at_raw)
        if due_at <= now_local():
            score += 20.0
        else:
            remaining_hours = max((due_at - now_local()).total_seconds() / 3600.0, 0.0)
            score -= min(12.0, remaining_hours / 6.0)
    elif snapshot["total"] == 0:
        score += 6.0

    score += question.get("top_domain_confidence", 0.0) * 3.0
    return score


def domain_filter_match(question: Dict[str, object], requested: Optional[str]) -> bool:
    if not requested:
        return True
    requested_key = normalize_key(requested)
    domain_key = question["top_domain"]
    domain_labels = [
        TOP_DOMAINS[domain_key]["label"],
        TOP_DOMAINS[domain_key]["label_ja"],
        domain_key,
    ]
    return any(requested_key in normalize_key(label) or normalize_key(label) in requested_key for label in domain_labels)


def pick_questions(payload: Dict[str, object], state: Dict[str, object], count: int = 1, domain: Optional[str] = None) -> List[Dict[str, object]]:
    pool = [q for q in payload["questions"] if domain_filter_match(q, domain)]
    ranked = sorted(pool, key=lambda question: (-priority_score(question, state), question["global_index"]))
    return ranked[:count]


def docs_for_question(question: Dict[str, object]) -> List[str]:
    links = list(question.get("doc_urls", []))
    if links:
        return links[:3]
    topics = [topic for topic in question.get("learn_more_topics", []) if topic]
    if topics:
        return [docs_search_url(topic) for topic in topics[:3]]
    fallback_topics = []
    if question.get("learning_domains"):
        fallback_topics.append(question["learning_domains"][0])
    prompt_key = normalize_key(question["prompt"])
    for needle, topic in DOC_TOPIC_HINTS:
        if needle in prompt_key and topic not in fallback_topics:
            fallback_topics.append(topic)
            break
    fallback_topics.append(TOP_DOMAINS[question["top_domain"]]["label"])
    deduped = []
    for topic in fallback_topics:
        if topic and topic not in deduped:
            deduped.append(topic)
    return [docs_search_url(topic) for topic in deduped[:2]]


def format_question(question: Dict[str, object]) -> str:
    lines = [
        f"{question['id']} | Set {question['source_set']} Q{question['source_number']}",
        f"Domain: {TOP_DOMAINS[question['top_domain']]['label']} ({question['top_domain_confidence']:.2f})",
        f"Prompt: {question['prompt_ja']}",
    ]
    if question["prompt_ja"] != question["prompt"]:
        lines.append(f"Original: {question['prompt']}")
    for choice in question["choices"]:
        lines.append(f"{choice['id']}. {choice['text_ja']}")
    if question.get("multi_select"):
        lines.append(f"Answer format: comma-separated ({question['choose_count']}つ)")
    else:
        lines.append("Answer format: A / B / C / D")
    return "\n".join(lines)


def evaluate_answer(question: Dict[str, object], answer: str) -> Tuple[bool, List[str], List[str]]:
    user_ids = answer_tokens(answer)
    correct_ids = sorted(question.get("correct_choice_ids", []))
    return user_ids == correct_ids, user_ids, correct_ids


def record_attempt(state: Dict[str, object], question: Dict[str, object], user_ids: List[str], correct: bool) -> Dict[str, object]:
    attempts = state.setdefault("attempts", {})
    record = attempts.setdefault(question["id"], {"total": 0, "correct": 0, "streak": 0, "history": []})
    record["total"] = int(record.get("total", 0)) + 1
    if correct:
        record["correct"] = int(record.get("correct", 0)) + 1
        record["streak"] = int(record.get("streak", 0)) + 1
    else:
        record["streak"] = 0
    record["last_seen"] = iso_now()
    record["last_result"] = correct
    record["last_answer"] = user_ids
    record["due_at"] = spaced_repetition_due(correct, int(record.get("streak", 0))).isoformat(timespec="seconds")
    history = record.setdefault("history", [])
    history.append(
        {
            "at": iso_now(),
            "answer": user_ids,
            "correct": correct,
        }
    )
    if len(history) > 20:
        del history[:-20]
    return record


def report_stats(payload: Dict[str, object], state: Dict[str, object]) -> Dict[str, object]:
    domain_stats: Dict[str, Dict[str, float]] = {}
    for domain_key in TOP_DOMAINS:
        domain_stats[domain_key] = {"total": 0.0, "correct": 0.0}

    for question in payload["questions"]:
        snapshot = attempt_snapshot(question, state)
        domain_stats[question["top_domain"]]["total"] += snapshot["total"]
        domain_stats[question["top_domain"]]["correct"] += snapshot["correct"]

    weighted_accuracy = 0.0
    rows = []
    for domain_key, meta in TOP_DOMAINS.items():
        total = domain_stats[domain_key]["total"]
        correct = domain_stats[domain_key]["correct"]
        accuracy = (correct / total) if total else 0.0
        weighted_accuracy += accuracy * meta["weight"]
        rows.append(
            {
                "domain_key": domain_key,
                "label": meta["label"],
                "label_ja": meta["label_ja"],
                "weight": meta["weight"],
                "total": int(total),
                "correct": int(correct),
                "accuracy": accuracy,
            }
        )

    attempted = sum(int(record.get("total", 0)) for record in state.get("attempts", {}).values())
    reviewed = len(state.get("attempts", {}))
    coverage = min(1.0, reviewed / max(1, payload["question_count"]))
    readiness = weighted_accuracy
    pass_probability = max(0.05, min(0.98, 0.35 + readiness * 0.65 + coverage * 0.10))
    weakest = sorted(rows, key=lambda row: row["accuracy"])[:3]
    return {
        "rows": rows,
        "weighted_accuracy": readiness,
        "attempted": attempted,
        "reviewed": reviewed,
        "pass_probability": pass_probability,
        "weakest": weakest,
    }


def domain_targets(total: int) -> Dict[str, int]:
    quotas = {key: int(meta["weight"] * total) for key, meta in TOP_DOMAINS.items()}
    remainder = total - sum(quotas.values())
    ranked = sorted(
        TOP_DOMAINS,
        key=lambda key: (TOP_DOMAINS[key]["weight"] * total) - int(TOP_DOMAINS[key]["weight"] * total),
        reverse=True,
    )
    for key in ranked[:remainder]:
        quotas[key] += 1
    return quotas


def question_blob_ja(question: Dict[str, object]) -> str:
    parts = [question.get("prompt_ja", ""), question.get("overall_explanation_ja", "")]
    parts.extend(choice.get("text_ja", "") for choice in question.get("choices", []))
    return normalize_key(" ".join(part for part in parts if part))


def scenario_question(question: Dict[str, object]) -> bool:
    prompt = question.get("prompt_ja", "")
    return len(prompt) >= 70 or prompt.startswith(("あなたは", "ある", "企業", "大手", "国際", "多国籍"))


def extract_topic_tags(question: Dict[str, object]) -> List[str]:
    blob = question_blob_ja(question)
    tags: List[str] = []
    for tag, patterns in CURATION_TOPIC_TAGS.get(question["top_domain"], {}).items():
        if any(pattern in blob for pattern in patterns):
            tags.append(tag)
    return tags


def extract_adaptive_tags(question: Dict[str, object]) -> List[str]:
    blob = question_blob_ja(question)
    tags: List[str] = []
    for tag, patterns in ADAPTIVE_CONCEPT_TAGS.get(question["top_domain"], {}).items():
        if any(pattern in blob for pattern in patterns):
            tags.append(tag)
    return tags


def current_release_tags(adaptive_tags: List[str]) -> List[str]:
    return [tag for tag in adaptive_tags if tag in CURRENT_RELEASE_PRIORITY_TAGS]


def base_difficulty_seed(question: Dict[str, object], adaptive_tags: List[str]) -> float:
    difficulty = 0.48
    if question.get("multi_select"):
        difficulty += 0.08
    difficulty += min(0.08, len(adaptive_tags) * 0.015)
    if question.get("source_status_correct") is False:
        difficulty += 0.04
    if scenario_question(question):
        difficulty += 0.03
    if "application_access_control" in adaptive_tags or "importing_data" in adaptive_tags:
        difficulty += 0.04
    if "platform_overview" in adaptive_tags or "service_catalog" in adaptive_tags:
        difficulty -= 0.02
    return round(max(0.28, min(0.88, difficulty)), 3)


def narrow_scope_hits(question: Dict[str, object]) -> List[str]:
    blob = question_blob_ja(question)
    return [pattern for pattern in NARROW_SCOPE_PATTERNS if pattern in blob]


def curation_score(question: Dict[str, object]) -> Tuple[float, List[str], List[str]]:
    score = 0.0
    reasons: List[str] = []

    if question["source_set"] >= 10:
        score += 24.0
        reasons.append("新しめの高品質バンク")
    elif question["source_set"] >= 6:
        score += 12.0
        reasons.append("日本語バンク")
    else:
        score += 4.0

    if question.get("learning_domains"):
        score += 12.0
        reasons.append("学習領域メタデータあり")
    if question.get("doc_urls"):
        score += 8.0
        reasons.append("公式リンクあり")
    if question.get("overall_explanation"):
        score += 8.0
        reasons.append("解説が充実")

    confidence = float(question.get("top_domain_confidence", 0.0))
    score += confidence * 12.0
    if confidence >= 0.8:
        reasons.append("ドメイン一致度が高い")

    if question.get("multi_select"):
        score += 4.0
        reasons.append("本番で落としやすい複数選択")
    elif int(question.get("choose_count", 1)) == 1:
        score += 2.0

    if scenario_question(question):
        score += 3.0
        reasons.append("シナリオ文脈つき")

    difficulty = normalize_key(str(question.get("difficulty") or ""))
    if any(token in difficulty for token in ("easy", "medium", "易", "中")):
        score += 3.0

    if question.get("source_status_correct") is False:
        score += 2.0

    topic_tags = extract_topic_tags(question)
    if topic_tags:
        score += min(12.0, len(topic_tags) * 3.0)
        reasons.append("コア論点: " + ", ".join(topic_tags[:3]))
    else:
        score -= 4.0

    adaptive_tags = extract_adaptive_tags(question)
    release_tags = current_release_tags(adaptive_tags)
    if release_tags:
        score += min(10.0, len(release_tags) * 4.0)
        reasons.append("2026現行トピック: " + ", ".join(release_tags[:2]))

    narrow_hits = narrow_scope_hits(question)
    if narrow_hits:
        score -= min(10.0, len(narrow_hits) * 4.0)

    return score, reasons[:4], topic_tags


def cluster_key(question: Dict[str, object], topic_tags: List[str]) -> str:
    correct_texts = [
        choice.get("text_ja", "")
        for choice in question.get("choices", [])
        if choice.get("id") in question.get("correct_choice_ids", [])
    ]
    answer_key = normalize_key(" | ".join(correct_texts))[:120]
    tag_key = "|".join(sorted(topic_tags)[:3])
    return f"{question['top_domain']}|{tag_key}|{answer_key}"


def study_plan(curated_questions: List[Dict[str, object]], days: int, daily_hours: float) -> Dict[str, object]:
    quotas = domain_targets(len(curated_questions))
    review_focus = [
        "database_management_platform_security",
        "self_service_automation",
        "configuring_applications_for_collaboration",
        "data_migration_integration",
        "instance_configuration",
        "platform_overview_navigation",
    ]
    daily_new_targets = [34, 34, 36, 36, 38, 40, 0, 34, 36, 36, 38, 0, 28, 0]
    daily_review_targets = [8, 10, 10, 12, 12, 14, 20, 12, 12, 14, 14, 15, 20, 25]
    if days != 14:
        daily_new_targets = [max(28, round(len(curated_questions) * 0.72 / days)) for _ in range(days)]
        daily_review_targets = [max(10, round(len(curated_questions) * 0.28 / days)) for _ in range(days)]

    remaining = dict(quotas)
    schedule = []
    domain_rotation = [
        "database_management_platform_security",
        "self_service_automation",
        "configuring_applications_for_collaboration",
        "data_migration_integration",
        "instance_configuration",
        "platform_overview_navigation",
    ]

    for day in range(days):
        focus_domains = domain_rotation[day % len(domain_rotation) :] + domain_rotation[: day % len(domain_rotation)]
        new_count = daily_new_targets[day]
        review_count = daily_review_targets[day]
        is_mock_day = day == 11
        is_final_day = day == days - 1

        domain_split = []
        if new_count:
            active_domains = [key for key in focus_domains if remaining.get(key, 0) > 0]
            if not active_domains:
                active_domains = list(TOP_DOMAINS.keys())
            weights = [remaining.get(key, 0) or 1 for key in active_domains]
            total_weight = sum(weights)
            assigned = 0
            for idx, key in enumerate(active_domains):
                if idx == len(active_domains) - 1:
                    portion = new_count - assigned
                else:
                    portion = round(new_count * (weights[idx] / total_weight))
                    portion = min(portion, remaining.get(key, 0))
                if portion <= 0:
                    continue
                domain_split.append({"domain_key": key, "count": portion})
                assigned += portion
                remaining[key] = max(0, remaining[key] - portion)

            while assigned < new_count:
                refill = max(active_domains, key=lambda key: remaining.get(key, 0))
                target = next((item for item in domain_split if item["domain_key"] == refill), None)
                if target is None:
                    domain_split.append({"domain_key": refill, "count": 1})
                else:
                    target["count"] += 1
                assigned += 1
                remaining[refill] = max(0, remaining.get(refill, 0) - 1)

        message = "弱点を潰す日"
        if is_mock_day:
            message = "60問模試 + 復習"
        elif is_final_day:
            message = "弱点総仕上げ"
        elif day < 6:
            message = "新規理解を積む日"
        elif day < 12:
            message = "定着と再出題を回す日"

        schedule.append(
            {
                "day": day + 1,
                "label": f"Day {day + 1}",
                "message": message,
                "estimated_hours": daily_hours,
                "new_questions_target": new_count,
                "review_questions_target": review_count,
                "mock_questions": 60 if is_mock_day else 0,
                "domain_split": domain_split,
                "review_focus": review_focus[:3] if day < 7 else review_focus[:4],
            }
        )

    return {
        "days": days,
        "daily_hours": daily_hours,
        "daily_attempt_target": round(sum(item["new_questions_target"] + item["review_questions_target"] + item["mock_questions"] for item in schedule) / days),
        "schedule": schedule,
    }


def build_curated_payload(payload: Dict[str, object], count: int, days: int, daily_hours: float) -> Dict[str, object]:
    quotas = domain_targets(count)
    scored = []
    for question in payload["questions"]:
        score, reasons, topic_tags = curation_score(question)
        adaptive_tags = extract_adaptive_tags(question)
        release_tags = current_release_tags(adaptive_tags)
        scored.append(
            {
                "question": question,
                "score": score,
                "reasons": reasons,
                "topic_tags": topic_tags,
                "adaptive_tags": adaptive_tags,
                "release_tags": release_tags,
                "base_difficulty": base_difficulty_seed(question, adaptive_tags),
                "cluster_key": cluster_key(question, topic_tags),
            }
        )

    by_domain: Dict[str, List[Dict[str, object]]] = {key: [] for key in TOP_DOMAINS}
    for item in scored:
        by_domain[item["question"]["top_domain"]].append(item)
    for domain_key in by_domain:
        by_domain[domain_key].sort(
            key=lambda item: (-item["score"], -item["question"]["source_set"], item["question"]["global_index"])
        )

    selected: List[Dict[str, object]] = []
    selected_ids = set()
    domain_counts = {key: 0 for key in TOP_DOMAINS}
    cluster_counts: Dict[str, int] = {}

    for cluster_cap in (1, 2, 99):
        for domain_key, target in quotas.items():
            if domain_counts[domain_key] >= target:
                continue
            for item in by_domain[domain_key]:
                if domain_counts[domain_key] >= target:
                    break
                question = item["question"]
                if question["id"] in selected_ids:
                    continue
                current_cluster_count = cluster_counts.get(item["cluster_key"], 0)
                if current_cluster_count >= cluster_cap:
                    continue
                cluster_counts[item["cluster_key"]] = current_cluster_count + 1
                domain_counts[domain_key] += 1
                selected_ids.add(question["id"])
                selected.append(item)

    selected_questions = []
    for curated_index, item in enumerate(selected, start=1):
        question = item["question"]
        selected_questions.append(
            {
                "curated_index": curated_index,
                "id": question["id"],
                "prompt": question["prompt_ja"],
                "original_prompt": question["prompt"],
                "language": question["language"],
                "domain_key": question["top_domain"],
                "domain_label": TOP_DOMAINS[question["top_domain"]]["label"],
                "domain_label_ja": TOP_DOMAINS[question["top_domain"]]["label_ja"],
                "choices": [
                    {
                        "id": choice["id"],
                        "text": choice["text_ja"],
                        "original_text": choice["text"],
                    }
                    for choice in question["choices"]
                ],
                "correct_choice_ids": question["correct_choice_ids"],
                "multi_select": question["multi_select"],
                "choose_count": question["choose_count"],
                "explanation": question["overall_explanation_ja"] or question["overall_explanation"],
                "docs": docs_for_question(question),
                "yield_score": round(item["score"], 2),
                "yield_reasons": item["reasons"],
                "topic_tags": item["topic_tags"],
                "concept_tags": item["adaptive_tags"],
                "current_service_tags": item["release_tags"],
                "current_relevance_score": round(min(1.0, 0.22 + len(item["release_tags"]) * 0.22), 2),
                "base_difficulty": item["base_difficulty"],
                "exam_weight": TOP_DOMAINS[question["top_domain"]]["weight"],
                "source_set": question["source_set"],
                "source_number": question["source_number"],
                "source_status_correct": question["source_status_correct"],
            }
        )

    domain_inventory = []
    for domain_key, target in quotas.items():
        picked = [question for question in selected_questions if question["domain_key"] == domain_key]
        domain_inventory.append(
            {
                "domain_key": domain_key,
                "label": TOP_DOMAINS[domain_key]["label"],
                "label_ja": TOP_DOMAINS[domain_key]["label_ja"],
                "weight": TOP_DOMAINS[domain_key]["weight"],
                "target_count": target,
                "actual_count": len(picked),
            }
        )

    plan = study_plan(selected_questions, days=days, daily_hours=daily_hours)
    return {
        "built_at": iso_now(),
        "source": payload["source"],
        "selection_policy": [
            "2026年1月更新の公式CSAブループリント配分で600問に圧縮",
            "高品質バンク・学習領域メタデータ・解説の厚さを優先",
            "2026年4月時点の現行ServiceNow文脈に近いトピックを追加加点",
            "コア論点の被りを抑えつつ、弱点化しやすい複数選択を少し厚めに採用",
            "2週間・1日2-3時間の前提で回せる量に制限",
        ],
        "official_context": OFFICIAL_EXAM_CONTEXT,
        "meta": {
            "curated_count": len(selected_questions),
            "full_question_count": payload["question_count"],
            "study_days": days,
            "daily_hours": daily_hours,
        },
        "domains": domain_inventory,
        "plan": plan,
        "questions": selected_questions,
    }


def save_curated_payload(curated: Dict[str, object]) -> None:
    ensure_runtime_dir()
    CURATED_PATH.write_text(json.dumps(curated, ensure_ascii=False, indent=2), encoding="utf-8")


def load_curated_payload() -> Dict[str, object]:
    if not CURATED_PATH.exists():
        raise SystemExit("先に `python3 csa_spartan.py curate` を実行してください。")
    return json.loads(CURATED_PATH.read_text(encoding="utf-8"))


def export_web_data(curated: Dict[str, object]) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DATA_PATH.write_text(json.dumps(curated, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def start_mock_session(payload: Dict[str, object], state: Dict[str, object], count: int, minutes: int) -> Dict[str, object]:
    selected = pick_questions(payload, state, count=count)
    session_id = f"mock-{now_local().strftime('%Y%m%d-%H%M%S')}"
    session = {
        "id": session_id,
        "kind": "mock",
        "started_at": iso_now(),
        "ends_at": (now_local() + timedelta(minutes=minutes)).isoformat(timespec="seconds"),
        "question_ids": [question["id"] for question in selected],
        "answers": {},
        "minutes": minutes,
    }
    state.setdefault("sessions", {})[session_id] = session
    save_state(state)
    return session


def find_question(payload: Dict[str, object], question_id: str) -> Dict[str, object]:
    for question in payload["questions"]:
        if question["id"] == question_id:
            return question
    raise SystemExit(f"問題IDが見つからない: {question_id}")


def print_build_summary(payload: Dict[str, object]) -> None:
    questions = payload["questions"]
    lang_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {key: 0 for key in TOP_DOMAINS}
    for question in questions:
        lang_counts[question["language"]] = lang_counts.get(question["language"], 0) + 1
        domain_counts[question["top_domain"]] += 1
    print(f"Built: {payload['question_count']} questions")
    print(f"Source: {payload['source']}")
    print(f"Languages: {lang_counts}")
    print("Domains:")
    for domain_key, count in domain_counts.items():
        print(f"  - {TOP_DOMAINS[domain_key]['label']}: {count}")


def cmd_build(args: argparse.Namespace) -> None:
    payload = build_dataset(Path(args.source).expanduser(), force=args.force)
    print_build_summary(payload)


def cmd_curate(args: argparse.Namespace) -> None:
    payload = build_dataset(Path(args.source).expanduser(), force=args.force)
    curated = build_curated_payload(payload, count=args.count, days=args.days, daily_hours=args.daily_hours)
    save_curated_payload(curated)
    print(f"Curated: {curated['meta']['curated_count']} / {curated['meta']['full_question_count']}")
    for domain in curated["domains"]:
        print(f"  - {domain['label']}: {domain['actual_count']} questions")


def cmd_web_build(args: argparse.Namespace) -> None:
    payload = build_dataset(Path(args.source).expanduser(), force=args.force)
    curated = build_curated_payload(payload, count=args.count, days=args.days, daily_hours=args.daily_hours)
    save_curated_payload(curated)
    export_web_data(curated)
    print(f"Exported: {WEB_DATA_PATH}")
    print(f"Questions: {curated['meta']['curated_count']}")


def cmd_next(args: argparse.Namespace) -> None:
    payload = load_questions()
    state = load_state()
    question = pick_questions(payload, state, count=1, domain=args.domain)[0]
    print(format_question(question))


def cmd_answer(args: argparse.Namespace) -> None:
    payload = load_questions()
    state = load_state()
    question = find_question(payload, args.question_id)
    correct, user_ids, correct_ids = evaluate_answer(question, args.answer)
    record_attempt(state, question, user_ids, correct)
    save_state(state)
    print("RESULT:", "正解" if correct else "不正解")
    print("Your answer:", ",".join(user_ids) or "(blank)")
    print("Correct:", ",".join(correct_ids) or "(unknown)")
    explanation = question["overall_explanation_ja"] or question["overall_explanation"] or "解説がありません。"
    print("Explanation:", explanation)
    docs = docs_for_question(question)
    if docs:
        print("Docs:")
        for link in docs:
            print(f"  - {link}")


def cmd_report(args: argparse.Namespace) -> None:
    payload = load_questions()
    state = load_state()
    stats = report_stats(payload, state)
    print(f"Weighted readiness: {stats['weighted_accuracy'] * 100:.1f}%")
    print(f"Estimated pass probability: {stats['pass_probability'] * 100:.1f}%")
    print(f"Reviewed questions: {stats['reviewed']} / {payload['question_count']}")
    print("Domain accuracy:")
    for row in stats["rows"]:
        print(
            f"  - {row['label']}: {row['accuracy'] * 100:.1f}% "
            f"(correct {row['correct']} / total {row['total']}, weight {row['weight'] * 100:.0f}%)"
        )
    print("Weakest domains:")
    for row in stats["weakest"]:
        print(f"  - {row['label']}: {row['accuracy'] * 100:.1f}%")


def cmd_today(args: argparse.Namespace) -> None:
    payload = load_questions()
    state = load_state()
    stats = report_stats(payload, state)
    weakest = stats["weakest"]
    due_now = []
    for question in payload["questions"]:
        snapshot = attempt_snapshot(question, state)
        due_at = snapshot["due_at"]
        if due_at and datetime.fromisoformat(due_at) <= now_local():
            due_now.append(question["id"])
        elif question.get("source_status_correct") is False and snapshot["record"].get("total", 0) == 0:
            due_now.append(question["id"])
    target = max(20, min(40, len(due_now) if due_now else 25))
    print(f"今日の目標: {target}問")
    print(f"合格見込み(推定): {stats['pass_probability'] * 100:.1f}%")
    print("重点分野:")
    for row in weakest:
        print(f"  - {row['label']}: 正答率 {row['accuracy'] * 100:.1f}%")
    print(f"再出題待ち/優先問題: {len(due_now)}問")


def cmd_mock_start(args: argparse.Namespace) -> None:
    payload = load_questions()
    state = load_state()
    session = start_mock_session(payload, state, count=args.count, minutes=args.minutes)
    first_question = find_question(payload, session["question_ids"][0])
    print(f"Session: {session['id']}")
    print(f"Time limit: {args.minutes} minutes")
    print(format_question(first_question))


def cmd_mock_answer(args: argparse.Namespace) -> None:
    payload = load_questions()
    state = load_state()
    sessions = state.get("sessions", {})
    session = sessions.get(args.session_id)
    if not session:
        raise SystemExit(f"セッションが見つからない: {args.session_id}")
    if args.question_id not in session["question_ids"]:
        raise SystemExit("この問題はセッションに含まれていません。")
    question = find_question(payload, args.question_id)
    correct, user_ids, correct_ids = evaluate_answer(question, args.answer)
    session["answers"][args.question_id] = {"answer": user_ids, "correct": correct, "at": iso_now()}
    record_attempt(state, question, user_ids, correct)
    save_state(state)
    answered = len(session["answers"])
    remaining = len(session["question_ids"]) - answered
    print("RESULT:", "正解" if correct else "不正解")
    print("Correct:", ",".join(correct_ids))
    print("Remaining:", remaining)
    print("Explanation:", question["overall_explanation_ja"] or question["overall_explanation"] or "解説なし")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CSA Spartan Master CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="RTFを解析して学習データを構築")
    build.add_argument("--source", default=str(DEFAULT_SOURCE))
    build.add_argument("--force", action="store_true")
    build.set_defaults(func=cmd_build)

    curate = sub.add_parser("curate", help="1434問から600問の高頻出学習バンクを生成")
    curate.add_argument("--source", default=str(DEFAULT_SOURCE))
    curate.add_argument("--force", action="store_true")
    curate.add_argument("--count", type=int, default=CURATED_BANK_SIZE)
    curate.add_argument("--days", type=int, default=DEFAULT_STUDY_DAYS)
    curate.add_argument("--daily-hours", type=float, default=DEFAULT_DAILY_HOURS)
    curate.set_defaults(func=cmd_curate)

    web_build = sub.add_parser("web-build", help="Webアプリ用データを書き出す")
    web_build.add_argument("--source", default=str(DEFAULT_SOURCE))
    web_build.add_argument("--force", action="store_true")
    web_build.add_argument("--count", type=int, default=CURATED_BANK_SIZE)
    web_build.add_argument("--days", type=int, default=DEFAULT_STUDY_DAYS)
    web_build.add_argument("--daily-hours", type=float, default=DEFAULT_DAILY_HOURS)
    web_build.set_defaults(func=cmd_web_build)

    nxt = sub.add_parser("next", help="次の優先問題を表示")
    nxt.add_argument("--domain", default=None)
    nxt.set_defaults(func=cmd_next)

    answer = sub.add_parser("answer", help="回答を記録")
    answer.add_argument("question_id")
    answer.add_argument("answer")
    answer.set_defaults(func=cmd_answer)

    report = sub.add_parser("report", help="進捗レポート")
    report.set_defaults(func=cmd_report)

    today = sub.add_parser("today", help="今日の学習目標")
    today.set_defaults(func=cmd_today)

    mock_start = sub.add_parser("mock-start", help="60問模試を開始")
    mock_start.add_argument("--count", type=int, default=60)
    mock_start.add_argument("--minutes", type=int, default=90)
    mock_start.set_defaults(func=cmd_mock_start)

    mock_answer = sub.add_parser("mock-answer", help="模試の回答を記録")
    mock_answer.add_argument("session_id")
    mock_answer.add_argument("question_id")
    mock_answer.add_argument("answer")
    mock_answer.set_defaults(func=cmd_mock_answer)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
