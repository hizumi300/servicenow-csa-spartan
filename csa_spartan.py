#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import os
import json
import math
import random
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

import numpy as np
import torch
from scipy.sparse import hstack
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / ".csa_spartan"
QUESTIONS_PATH = RUNTIME_DIR / "questions.json"
STATE_PATH = RUNTIME_DIR / "state.json"
CURATED_PATH = RUNTIME_DIR / "curated_600.json"
SHADOW_DIR = RUNTIME_DIR / "shadow"
SHADOW_REPORT_PATH = SHADOW_DIR / "shadow_report.json"
SHADOW_PROMOTION_PATH = SHADOW_DIR / "shadow_promotion.json"
DOCS_CACHE_PATH = RUNTIME_DIR / "official_docs_cache.json"
DOCS_DIR = ROOT / "docs"
WEB_DATA_DIR = DOCS_DIR / "data"
WEB_DATA_PATH = WEB_DATA_DIR / "csa600.json"
DEFAULT_SOURCE = Path.home() / "ServiseNow-CSA-Questions.rtfd" / "TXT.rtf"
OFFICIAL_DOCS_SEARCH_API = "https://www.servicenow.com/docs/api/khub/clustered-search"
OFFICIAL_DOCS_SEARCH_PAGE = "https://www.servicenow.com/docs/search"
OFFICIAL_DOCS_CACHE_TTL_HOURS = 18
OFFICIAL_DOCS_RELEASE_PRIORITY = {
    "australia": 6,
    "latest": 5,
    "zurich": 4,
    "yokohama": 3,
    "xanadu": 2,
    "washingtondc": 1,
}
DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "CSA_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
EMBEDDING_BATCH_SIZE = int(os.environ.get("CSA_EMBEDDING_BATCH_SIZE", "32"))

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
ACTIVE_POOL_MIN_SIZE = 420
ACTIVE_POOL_DEFAULT_SIZE = 480
ACTIVE_POOL_MAX_SIZE = 560

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

ACTIVE_POOL_MIN = ACTIVE_POOL_MIN_SIZE
ACTIVE_POOL_MAX = ACTIVE_POOL_MAX_SIZE
ACTIVE_POOL_DEFAULT = ACTIVE_POOL_DEFAULT_SIZE
DELTA_MODE_BOOST = 0.12

CONCEPT_LABELS_JA = {
    "platform_overview": "プラットフォーム概要",
    "the_instance": "インスタンス",
    "next_experience_unified_navigation": "Next Experience / Unified Navigation",
    "search_and_lists": "検索とリスト",
    "user_menu_and_roles": "ユーザーメニューとロール",
    "installing_applications_and_plugins": "アプリとプラグイン",
    "personalizing_customizing_instance": "個人設定とインスタンス調整",
    "common_user_interfaces": "共通UI",
    "instance_properties": "システムプロパティ",
    "lists_filters_tags": "リスト・フィルタ・タグ",
    "list_and_form_anatomy": "リスト/フォーム構造",
    "form_configuration": "フォーム設定",
    "task_management": "タスク管理",
    "visual_task_boards": "Visual Task Boards",
    "platform_analytics": "Platform Analytics",
    "notifications": "通知",
    "knowledge_management": "ナレッジ管理",
    "service_catalog": "サービスカタログ",
    "workflow_studio": "Workflow Studio",
    "virtual_agent": "Virtual Agent",
    "data_schema": "データスキーマ",
    "application_access_control": "Access Control",
    "importing_data": "データ取り込み",
    "cmdb_and_csdm": "CMDB / CSDM",
    "security_center": "Security Center",
    "shared_responsibility_model": "責任共有モデル",
    "ui_policies": "UI Policy",
    "business_rules": "Business Rule",
    "system_update_sets": "Update Set",
    "scripting_in_servicenow": "ServiceNowスクリプト",
}

CURRENT_SERVICE_LABELS_JA = {
    "next_experience_unified_navigation": "Unified Navigation",
    "platform_analytics": "Platform Analytics",
    "workflow_studio": "Workflow Studio",
    "virtual_agent": "Virtual Agent",
    "security_center": "Security Center",
    "shared_responsibility_model": "責任共有モデル",
}

CONCEPT_COACH_NOTES = {
    "platform_overview": "Now Platform は業務アプリの基盤だ。個別機能名ではなく、何を実現する土台かで判断しろ。",
    "the_instance": "インスタンスは 1 つの ServiceNow 環境だ。設定・データ・URL をまとめて捉えろ。",
    "next_experience_unified_navigation": "Unified Navigation は上部ナビで横断操作を担う。検索、通知、ワークスペース切替をここに結び付けろ。",
    "search_and_lists": "検索とリストは『今あるデータを探して絞る』ための機能だ。フィルタ、グループ化、タグを区別しろ。",
    "user_menu_and_roles": "Impersonate や権限昇格はユーザーメニュー起点だ。誰が実行できるかはロールで決まる。",
    "installing_applications_and_plugins": "アプリやプラグインは機能有効化の入口だ。依存関係と有効化範囲を見落とすな。",
    "personalizing_customizing_instance": "個人設定とインスタンス全体設定を混同するな。誰に効く変更かで切り分けろ。",
    "common_user_interfaces": "Workspace、Classic UI、リスト、フォームは役割が違う。UI 種別を問われたらここだ。",
    "instance_properties": "System Properties は動作切替の全体設定だ。画面レイアウト変更とは別物として覚えろ。",
    "lists_filters_tags": "リスト操作は並び替え、フィルタ、タグ、グループ化が中心だ。閲覧効率系の定番論点だ。",
    "list_and_form_anatomy": "関連リンク、関連リスト、コンテキストメニューなど、部品名を正確に区別しろ。",
    "form_configuration": "フォーム表示の構成変更と、辞書レベルのデータ定義変更を混ぜるな。",
    "task_management": "Task 系は共通 Task テーブル前提で考える。割当、状態、活動記録の共通性が軸だ。",
    "visual_task_boards": "VTB はカード型で作業を可視化する UI だ。ACL やテーブル設計の話ではない。",
    "platform_analytics": "Report は現在の状態、Analytics は時系列の傾向だ。この切り分けを外すな。",
    "notifications": "通知は『誰に、いつ、何を送るか』で整理しろ。トリガ、受信者、本文を分けて考えろ。",
    "knowledge_management": "ナレッジは記事管理、公開条件、検索性が論点だ。単なる添付やメールとは違う。",
    "service_catalog": "Catalog Item、Record Producer、Order Guide の用途差は本番頻出だ。役割で覚えろ。",
    "workflow_studio": "Workflow Studio / Flow 系は自動化の設計と再利用が軸だ。手作業運用と混同するな。",
    "virtual_agent": "Virtual Agent は会話導線で自己解決を促す。通常フォーム入力との違いを押さえろ。",
    "data_schema": "テーブル、フィールド、参照、拡張はデータ構造の問題だ。表示設定の話ではない。",
    "application_access_control": "ACL は条件、ロール、スクリプトの積で判定する。見えるか書けるかはここで決まる。",
    "importing_data": "Data Source → Import Set → Transform Map → Coalesce の流れで整理しろ。",
    "cmdb_and_csdm": "CMDB は CI 管理、CSDM はその整理モデルだ。資産台帳と混同するな。",
    "security_center": "Security Center はセキュリティ状態を可視化し統制する入口だ。個別 ACL の代替ではない。",
    "shared_responsibility_model": "責任共有モデルでは ServiceNow 側と顧客側の責任を分けて考える。設定と運用の多くは顧客責任だ。",
    "ui_policies": "UI Policy は見た目や必須/読取専用の制御だ。DB 更新ロジックではない。",
    "business_rules": "Business Rule はサーバー側ロジックだ。保存前後や表示時など、実行タイミングで切れ。",
    "system_update_sets": "Update Set は設定変更の移送だ。業務データ移行とは用途が違う。",
    "scripting_in_servicenow": "スクリプトはクライアントかサーバーかを先に分けろ。実行場所を外すな。",
}

DOMAIN_COACH_NOTES = {
    "platform_overview_navigation": "プラットフォーム全体の役割と、ナビゲーション部品の位置づけで判断しろ。",
    "instance_configuration": "個人設定か全体設定か、UI変更かプロパティ変更かを切り分けろ。",
    "configuring_applications_for_collaboration": "通知、レポート、フォーム部品、コラボ機能の役割差で判定しろ。",
    "self_service_automation": "Catalog、Knowledge、Virtual Agent、Flow の用途差を軸に切れ。",
    "database_management_platform_security": "テーブル、ACL、ロール、CMDB など、データ構造と権限で考えろ。",
    "data_migration_integration": "Import、Transform、Script、Update Set の責務と流れを整理しろ。",
}

SIMILARITY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "what",
    "which",
    "with",
    "you",
    "your",
    "using",
    "use",
    "when",
    "where",
    "次",
    "次の",
    "どれ",
    "どれですか",
    "何",
    "何ですか",
    "以下",
    "場合",
    "会社",
    "企業",
    "ユーザー",
}

CONFUSION_FAMILIES = {
    "ui_policy_data_policy_client_script": {
        "label_ja": "UI Policy / Data Policy / Client Script",
        "domains": {"instance_configuration", "data_migration_integration"},
        "groups": [
            ["ui policy", "ui policies", "uiポリシー"],
            ["data policy", "data policies", "データポリシー"],
            ["client script", "client scripts", "クライアントスクリプト"],
        ],
        "doc_topics": ["UI policies", "Data policies", "Client scripts"],
        "root_snippet": "UI Policy はフォーム表示制御、Data Policy は入力制約の強制、Client Script はクライアント側ロジックだ。",
    },
    "report_platform_analytics_dashboard": {
        "label_ja": "Report / Platform Analytics / Dashboard",
        "domains": {"configuring_applications_for_collaboration"},
        "groups": [
            ["report", "reports", "レポート"],
            ["platform analytics", "performance analytics", "analytics"],
            ["dashboard", "dashboards", "ダッシュボード"],
        ],
        "doc_topics": ["Reports", "Platform Analytics", "Dashboards"],
        "root_snippet": "Report は現在の集計や一覧、Platform Analytics は指標の傾向分析、Dashboard は可視化の置き場だ。",
    },
    "catalog_item_record_producer_order_guide": {
        "label_ja": "Catalog Item / Record Producer / Order Guide",
        "domains": {"self_service_automation"},
        "groups": [
            ["catalog item", "catalog items", "カタログアイテム", "service catalog", "サービスカタログ"],
            ["record producer", "record producers", "レコードプロデューサー"],
            ["order guide", "order guides", "オーダーガイド"],
        ],
        "doc_topics": ["Service Catalog", "Record Producers", "Order Guides"],
        "root_snippet": "Catalog Item は要求対象、Record Producer はレコード作成、Order Guide は複数依頼の束ね役だ。",
    },
    "role_acl_user_criteria": {
        "label_ja": "Role / ACL / User Criteria",
        "domains": {"database_management_platform_security"},
        "groups": [
            ["role", "roles", "ロール"],
            ["access control", "acl", "アクセス制御"],
            ["user criteria", "ユーザー基準"],
        ],
        "doc_topics": ["Roles", "Access control rules", "User criteria"],
        "root_snippet": "Role は権限の割当単位、ACL は実際のアクセス判定、User Criteria は表示対象の絞り込みだ。",
    },
    "import_set_transform_map_coalesce": {
        "label_ja": "Import Set / Transform Map / Coalesce",
        "domains": {"data_migration_integration", "database_management_platform_security"},
        "groups": [
            ["import set", "import sets", "インポートセット"],
            ["transform map", "transform maps", "変換マップ"],
            ["coalesce"],
        ],
        "doc_topics": ["Import Sets", "Transform Maps", "Coalesce"],
        "root_snippet": "Import Set は受け皿、Transform Map は変換定義、Coalesce は一致キーだ。流れを崩すな。",
    },
    "knowledge_article_kb_category": {
        "label_ja": "Knowledge Article / Knowledge Base / Category",
        "domains": {"configuring_applications_for_collaboration", "self_service_automation"},
        "groups": [
            ["knowledge article", "article", "記事"],
            ["knowledge base", "ナレッジベース"],
            ["category", "categories", "カテゴリ"],
        ],
        "doc_topics": ["Knowledge Management"],
        "root_snippet": "Article は個別記事、Knowledge Base は公開先の器、Category は整理軸だ。",
    },
    "workflow_studio_flow_designer_playbook": {
        "label_ja": "Workflow Studio / Flow Designer / Playbook",
        "domains": {"self_service_automation"},
        "groups": [
            ["workflow studio", "workflow"],
            ["flow designer", "subflow", "action designer"],
            ["playbook"],
        ],
        "doc_topics": ["Workflow Studio", "Flow Designer", "Playbook"],
        "root_snippet": "Workflow Studio は自動化設計の入口、Flow Designer はフロー本体、Playbook は作業導線の定義だ。",
    },
    "cmdb_csdm_configuration_item": {
        "label_ja": "CMDB / CSDM / Configuration Item",
        "domains": {"database_management_platform_security"},
        "groups": [
            ["cmdb"],
            ["csdm"],
            ["configuration item", "configuration items", "構成アイテム", "ci "],
        ],
        "doc_topics": ["CMDB", "Common Service Data Model"],
        "root_snippet": "CMDB は CI の保管庫、CSDM は整理モデル、Configuration Item は個々の管理対象だ。",
    },
}


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def sanitize_source_label(source: object) -> str:
    if source is None:
        return "ServiseNow-CSA-Questions"
    raw = str(source).strip()
    if not raw:
        return "ServiseNow-CSA-Questions"
    path = Path(raw)
    if path.name.lower() == "txt.rtf" and path.parent.name:
        parent_name = path.parent.name
        if parent_name.lower().endswith(".rtfd"):
            parent_name = parent_name[:-5]
        return parent_name or "ServiseNow-CSA-Questions"
    if path.stem and path.stem.lower() != "txt":
        return path.stem
    if path.name:
        return path.name
    return "ServiseNow-CSA-Questions"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.replace("\xa0", " "))
    return text.strip()


def normalize_key(text: str) -> str:
    text = normalize_text(text).lower()
    return re.sub(r"\s+", " ", text)


def contains_japanese(text: str) -> bool:
    return bool(text and JP_CHAR_RE.search(text))


def english_alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    ja_chars = len(JP_CHAR_RE.findall(text))
    en_chars = len(re.findall(r"[A-Za-z]", text))
    total = ja_chars + en_chars
    if total == 0:
        return 0.0
    return en_chars / total


def mostly_japanese(text: str, *, threshold: float = 0.18) -> bool:
    return contains_japanese(text) and english_alpha_ratio(text) <= threshold


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    SHADOW_DIR.mkdir(exist_ok=True)


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


def glossary_pattern(source: str) -> str:
    escaped = re.escape(source)
    if re.fullmatch(r"[A-Za-z0-9 /&().+\-]+", source):
        return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    return escaped


def apply_glossary(text: str) -> str:
    translated = text
    for source, target in sorted(GLOSSARY.items(), key=lambda item: len(item[0]), reverse=True):
        translated = re.sub(glossary_pattern(source), target, translated, flags=re.IGNORECASE)
    return translated


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

    translated = apply_glossary(translated)

    phrase_replacements = [
        (r"(?i)\bfor example\b", "たとえば"),
        (r"(?i)\bby default\b", "デフォルトでは"),
        (r"(?i)\bin real-time\b", "リアルタイムで"),
        (r"(?i)\bover time\b", "時間の経過に伴って"),
        (r"(?i)\bthe current state of\b", "現在の"),
        (r"(?i)\bcurrent state of\b", "現在の"),
        (r"(?i)\bfor testing purposes\b", "テスト目的で"),
        (r"(?i)\bthe primary way to\b", "するための主要な方法"),
        (r"(?i)\bthe primary way\b", "主要な方法"),
        (r"(?i)\bcan be used to\b", "に使用できます"),
        (r"(?i)\ballows users to\b", "を使用すると、ユーザーは"),
        (r"(?i)\ballows you to\b", "を使用すると、"),
        (r"(?i)\blets you\b", "を使用すると、"),
        (r"(?i)\benables you to\b", "を可能にします"),
        (r"(?i)\benables users to\b", "により、ユーザーは"),
        (r"(?i)\bused to\b", "に使用される"),
        (r"(?i)\bview and update\b", "表示および更新"),
        (r"(?i)\bview and edit\b", "表示および編集"),
        (r"(?i)\bview documents directly\b", "ドキュメントを直接表示"),
        (r"(?i)\bopen and edit\b", "開いて編集"),
        (r"(?i)\btrack and view\b", "追跡および表示"),
        (r"(?i)\bsingle pane\b", "単一ペイン"),
        (r"(?i)\bone-stop experience\b", "ワンストップ体験"),
        (r"(?i)\bdark theme\b", "ダークテーマ"),
        (r"(?i)\bdark mode\b", "ダークモード"),
        (r"(?i)\bidentity providers\b", "ID プロバイダ"),
        (r"(?i)\bpasscode\b", "パスコード"),
        (r"(?i)\bpush notifications\b", "プッシュ通知"),
        (r"(?i)\bmachine-learning\b", "機械学習"),
        (r"(?i)\band\b", "と"),
        (r"(?i)\bor\b", "または"),
        (r"(?i)\bwhile\b", "一方で"),
    ]
    for pattern, value in phrase_replacements:
        translated = re.sub(pattern, value, translated)

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
    elif translated.lower().startswith("you can use "):
        translated = re.sub(r"(?i)^you can use\s+", "", translated)
        translated = translated.rstrip(".?")
        translated = f"{translated} を使用できます。"
    elif translated.lower().startswith("you can "):
        translated = re.sub(r"(?i)^you can\s+", "", translated)
        translated = translated.rstrip(".?")
        translated = f"{translated} できます。"
    elif translated.lower().startswith("the following "):
        translated = re.sub(r"(?i)^the following\s+", "次の", translated)
    elif translated.lower().startswith("a "):
        translated = re.sub(r"(?i)^a\s+", "", translated)
    elif translated.lower().startswith("an "):
        translated = re.sub(r"(?i)^an\s+", "", translated)
    elif translated.lower().startswith("the "):
        translated = re.sub(r"(?i)^the\s+", "", translated)

    translated = translated.replace(" ,", "、").replace(", ", "、")
    translated = translated.replace(" ? ", "？ ").replace(" ?", "？")
    translated = translated.replace(" .", "。").replace(". ", "。 ")
    translated = re.sub(r"\s+", " ", translated)
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
        if pick_prompt_language(choice["text"]) == "en":
            choice["text_ja"] = translate_text_en(choice["text"])
        else:
            choice["text_ja"] = choice["text"]

    overall_explanation = " ".join(meta.get("overall_explanation_lines", [])).strip()
    if not overall_explanation:
        overall_explanation = infer_overall_explanation(choices)
    explanation_language = pick_prompt_language(overall_explanation)

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
        "overall_explanation_ja": overall_explanation if explanation_language == "ja" else translate_text_en(overall_explanation),
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
        "source": sanitize_source_label(source),
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


def load_json_cache(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_json_cache(path: Path, payload: Dict[str, object]) -> None:
    ensure_runtime_dir()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def iso_age_hours(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        then = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (now_local() - then).total_seconds() / 3600.0


def strip_html_tags(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<span[^>]*class=\"kwicmatch\"[^>]*>", "", text)
    text = re.sub(r"<span[^>]*class=\"kwicstring\"[^>]*>", "", text)
    text = re.sub(r"<span[^>]*class=\"kwictruncate\"[^>]*>", "…", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return normalize_text(text)


def question_domain_key(question_like: Dict[str, object]) -> str:
    return str(question_like.get("domain_key") or question_like.get("top_domain") or "")


def english_search_term(term: str) -> str:
    term = normalize_text(term)
    for tag, label in CONCEPT_LABELS_JA.items():
        if term == label:
            return tag.replace("_", " ")
    for tag, label in CURRENT_SERVICE_LABELS_JA.items():
        if term == label:
            return tag.replace("_", " ")
    for meta in TOP_DOMAINS.values():
        if term == meta["label_ja"]:
            return meta["label"]
    return term


def official_doc_query_from_basis(question_like: Dict[str, object]) -> str:
    basis = question_like.get("doc_basis") or {}
    if not isinstance(basis, dict):
        basis = {}
    basis_terms = [english_search_term(str(term)) for term in basis.get("basis_terms", []) if term]
    primary = english_search_term(str(basis.get("primary_topic") or ""))
    secondary = [english_search_term(str(term)) for term in basis.get("secondary_topics", []) if term]
    release_labels = [
        tag.replace("_", " ")
        for tag in question_like.get("current_service_tags", [])[:2]
        if isinstance(tag, str)
    ]

    generic_topics = {
        "Platform Overview & Navigation",
        "Instance Configuration",
        "Configuring Applications for Collaboration",
        "Self Service & Automation",
        "Database Management & Platform Security",
        "Data Migration & Integration",
        "プラットフォーム概要とナビゲーション",
        "インスタンス構成",
        "コラボレーション用アプリケーション構成",
        "セルフサービスと自動化",
        "データベース管理とプラットフォームセキュリティ",
        "データ移行と統合",
    }
    query_parts: List[str] = []
    if primary:
        query_parts.append(primary)
    if basis.get("basis_type") == "confusion_family":
        query_parts.extend(basis_terms[1:4])
    elif primary in generic_topics:
        query_parts.extend(basis_terms[1:3] + release_labels[:1])
    else:
        query_parts.extend(secondary[:2])
    for part in basis_terms:
        if len(query_parts) >= 4:
            break
        if part not in query_parts:
            query_parts.append(part)
    return " ".join(dedupe_preserve_order([part for part in query_parts if part])).strip()


def normalize_official_family(value: str) -> str:
    return normalize_key(value).replace(" ", "")


def metadata_values(item: Dict[str, object]) -> Dict[str, List[str]]:
    values: Dict[str, List[str]] = {}
    for entry in item.get("metadata", []) or []:
        key = entry.get("key")
        raw_values = entry.get("values") or []
        if not key:
            continue
        values[str(key)] = [normalize_text(str(value)) for value in raw_values if value is not None]
    return values


def flatten_official_search_result(payload: Dict[str, object]) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    for cluster in payload.get("results", []) or []:
        for entry in cluster.get("entries", []) or []:
            item = (
                entry.get("topic")
                or entry.get("map")
                or entry.get("document")
                or entry.get("unstructuredDocument")
                or entry.get("htmlPackage")
                or {}
            )
            meta = metadata_values(item)
            candidates.append(
                {
                    "type": entry.get("type") or item.get("editorialType"),
                    "title": normalize_text(item.get("title") or ""),
                    "url": item.get("readerUrl") or item.get("documentUrl") or item.get("topicUrl") or item.get("url"),
                    "excerpt": strip_html_tags(item.get("htmlExcerpt") or item.get("excerpt") or ""),
                    "family": [normalize_official_family(value) for value in meta.get("family", []) if value],
                    "product_name": meta.get("product_name", []),
                    "doc_type": meta.get("ft:document_type", [])[:1],
                    "updated_on": (
                        meta.get("ft:lastTechChange", [])[:1]
                        or meta.get("ft:lastEdition", [])[:1]
                        or meta.get("ft:lastPublication", [])[:1]
                    ),
                    "metadata": meta,
                }
            )
    return candidates


def score_official_doc_candidate(
    candidate: Dict[str, object],
    query: str,
    question_like: Dict[str, object],
) -> float:
    basis = question_like.get("doc_basis") or {}
    basis_terms = [normalize_key(term) for term in basis.get("basis_terms", []) if term]
    title_key = normalize_key(candidate.get("title") or "")
    excerpt_key = normalize_key(candidate.get("excerpt") or "")
    url_key = normalize_key(candidate.get("url") or "")
    query_terms = [term for term in lexical_tokens(query) if len(term) >= 3][:8]

    score = 0.0
    families = candidate.get("family", []) or []
    if families:
        score += max(OFFICIAL_DOCS_RELEASE_PRIORITY.get(family, 0) for family in families) * 9.0
    if candidate.get("type") == "TOPIC":
        score += 16.0
    elif candidate.get("type") == "MAP":
        score -= 4.0
    if any("api reference" in normalize_key(name) for name in candidate.get("product_name", [])):
        score -= 12.0
    if "api-reference" in url_key:
        score -= 10.0
    if "workflow studio" in normalize_key(query) and "classic workflow" in title_key:
        score -= 8.0
    title_hits = sum(1 for term in query_terms if term in title_key)
    excerpt_hits = sum(1 for term in query_terms if term in excerpt_key)
    basis_hits = sum(1 for term in basis_terms if term and (term in title_key or term in excerpt_key or term in url_key))
    score += title_hits * 6.0
    score += excerpt_hits * 2.4
    score += basis_hits * 4.0
    if basis.get("primary_topic") and normalize_key(str(basis["primary_topic"])) in title_key:
        score += 12.0
    if candidate.get("excerpt"):
        score += min(8.0, len(candidate["excerpt"]) / 42.0)
    return score


def official_doc_search_request(query: str) -> Dict[str, object]:
    return {
        "query": query,
        "clusterSortCriterions": [{"key": "family"}],
        "metadataFilters": [],
        "facets": [{"id": "family"}, {"id": "media"}, {"id": "product_name"}],
        "sort": [],
        "sortId": None,
        "paging": {"page": 1, "perPage": 8},
        "keywordMatch": None,
        "contentLocale": "en-US",
        "virtualField": "EVERYWHERE",
        "scope": "DEFAULT",
    }


def search_official_docs_live(query: str) -> Dict[str, object]:
    request = Request(
        OFFICIAL_DOCS_SEARCH_API,
        data=json.dumps(official_doc_search_request(query)).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def resolve_official_doc_evidence(
    question_like: Dict[str, object],
    *,
    force_refresh: bool = False,
    memory_cache: Optional[Dict[str, Dict[str, object]]] = None,
) -> Optional[Dict[str, object]]:
    query = official_doc_query_from_basis(question_like)
    if not query:
        return None

    cache_key = normalize_key(query)
    if memory_cache is not None and cache_key in memory_cache and not force_refresh:
        return memory_cache[cache_key]

    cache = load_json_cache(DOCS_CACHE_PATH)
    cached = cache.get(cache_key)
    if (
        not force_refresh
        and isinstance(cached, dict)
        and (age_hours := iso_age_hours(cached.get("fetched_at"))) is not None
        and age_hours <= OFFICIAL_DOCS_CACHE_TTL_HOURS
    ):
        if memory_cache is not None:
            memory_cache[cache_key] = cached
        return cached

    try:
        payload = search_official_docs_live(query)
        candidates = flatten_official_search_result(payload)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        if isinstance(cached, dict):
            return cached
        return None

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            score_official_doc_candidate(candidate, query, question_like),
            candidate.get("title") or "",
        ),
        reverse=True,
    )
    chosen = ranked[0]
    evidence = {
        "source": "servicenow-fluidtopics-live",
        "query": query,
        "title": chosen.get("title"),
        "url": chosen.get("url") or f"{OFFICIAL_DOCS_SEARCH_PAGE}?q={quote_plus(query)}",
        "snippet": chosen.get("excerpt") or "",
        "release_family": (chosen.get("family") or ["unknown"])[0],
        "product_name": (chosen.get("product_name") or [chosen.get("title") or ""])[0],
        "document_type": (chosen.get("doc_type") or [chosen.get("type") or "unknown"])[0],
        "updated_on": (chosen.get("updated_on") or [None])[0],
        "score": round(score_official_doc_candidate(chosen, query, question_like), 2),
        "fetched_at": iso_now(),
        "alternatives": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "release_family": (item.get("family") or ["unknown"])[0],
            }
            for item in ranked[1:3]
            if item.get("url")
        ],
    }
    cache[cache_key] = evidence
    save_json_cache(DOCS_CACHE_PATH, cache)
    if memory_cache is not None:
        memory_cache[cache_key] = evidence
    return evidence


def concept_label_ja(tag: str) -> str:
    return CONCEPT_LABELS_JA.get(tag, tag.replace("_", " "))


def current_service_label_ja(tag: str) -> str:
    return CURRENT_SERVICE_LABELS_JA.get(tag, concept_label_ja(tag))


def build_explanation_ja(
    question: Dict[str, object],
    concept_tags: List[str],
    release_tags: List[str],
) -> str:
    original = normalize_text(question.get("overall_explanation_ja") or question.get("overall_explanation") or "")
    if original and mostly_japanese(original):
        return original

    correct_texts = []
    for choice in question.get("choices", []):
        if choice.get("id") not in question.get("correct_choice_ids", []):
            continue
        text = normalize_text(choice.get("text_ja") or choice.get("text") or "")
        if mostly_japanese(text, threshold=0.22):
            correct_texts.append(text.rstrip("。"))

    concept_labels = [concept_label_ja(tag) for tag in concept_tags[:2]]
    concept_notes = [CONCEPT_COACH_NOTES[tag] for tag in concept_tags if tag in CONCEPT_COACH_NOTES][:2]
    release_labels = [current_service_label_ja(tag) for tag in release_tags[:2]]

    lines = [f"正解は {', '.join(question['correct_choice_ids'])}。"]
    if question.get("multi_select"):
        lines.append(f"複数選択だ。{question['choose_count']}個を外した時点で失点だ。")
    if correct_texts:
        lines.append(f"正答肢の要点: {' / '.join(correct_texts[:2])}。")
    if concept_labels:
        lines.append(f"論点: {' / '.join(concept_labels)}。")
    if concept_notes:
        lines.append("押さえる点: " + " ".join(concept_notes))
    elif question.get("top_domain") in DOMAIN_COACH_NOTES:
        lines.append("押さえる点: " + DOMAIN_COACH_NOTES[question["top_domain"]])
    if release_labels:
        lines.append(f"2026観点: {' / '.join(release_labels)}。")

    generated = " ".join(lines).strip()
    if generated:
        return generated
    return original or "正解根拠を日本語で補完中。まずは正答肢と公式ドキュメントのキーワードを結び付けろ。"


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


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def active_pool_bounds(curated_cap: int) -> Dict[str, int]:
    max_size = min(ACTIVE_POOL_MAX_SIZE, curated_cap)
    default_size = min(ACTIVE_POOL_DEFAULT_SIZE, max_size)
    min_size = min(ACTIVE_POOL_MIN_SIZE, default_size)
    return {
        "min_size": min_size,
        "default_size": default_size,
        "max_size": max_size,
        "curated_cap": curated_cap,
    }


def compact_similarity_text(text: str) -> str:
    normalized = normalize_key(apply_glossary(text))
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff]+", "", normalized)


def char_ngrams(text: str, n: int = 3) -> set[str]:
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[index : index + n] for index in range(len(text) - n + 1)}


def lexical_tokens(text: str) -> List[str]:
    normalized = normalize_key(apply_glossary(text))
    tokens = re.findall(r"[a-z0-9_./+\-]{2,}|[\u3040-\u30ff\u3400-\u9fff]{2,}", normalized)
    filtered = [
        token
        for token in tokens
        if token not in SIMILARITY_STOPWORDS and not token.isdigit() and len(token) > 1
    ]
    return dedupe_preserve_order(filtered)


def jaccard_score(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def detect_confusion_family(
    question: Dict[str, object],
    topic_tags: List[str],
    adaptive_tags: List[str],
) -> Optional[str]:
    blob = question_blob_ja(question)
    best_key: Optional[str] = None
    best_score = 0.0
    for family_key, meta in CONFUSION_FAMILIES.items():
        group_hits = 0
        raw_hits = 0
        for group in meta["groups"]:
            matched = [pattern for pattern in group if pattern in blob]
            if matched:
                group_hits += 1
                raw_hits += len(matched)
        if group_hits == 0:
            continue
        domain_match = question["top_domain"] in meta["domains"]
        if not domain_match and group_hits < 2:
            continue
        score = group_hits * 10.0 + min(5.0, raw_hits)
        if domain_match:
            score += 2.0
        if group_hits >= 2:
            score += 4.0
        if any(topic in family_key for topic in topic_tags + adaptive_tags):
            score += 1.5
        if score > best_score:
            best_key = family_key
            best_score = score
    return best_key


def question_similarity_meta(
    question: Dict[str, object],
    topic_tags: List[str],
    adaptive_tags: List[str],
) -> Dict[str, object]:
    prompt_text = normalize_text(question.get("prompt_ja") or question.get("prompt") or "")
    choice_text = " ".join(
        normalize_text(choice.get("text_ja") or choice.get("text") or "")
        for choice in question.get("choices", [])
    )
    answer_text = " ".join(
        normalize_text(choice.get("text_ja") or choice.get("text") or "")
        for choice in question.get("choices", [])
        if choice.get("id") in question.get("correct_choice_ids", [])
    )
    prompt_compact = compact_similarity_text(prompt_text)
    answer_compact = compact_similarity_text(answer_text)
    choice_compact = compact_similarity_text(choice_text)
    seed_terms = lexical_tokens(" ".join([prompt_text, answer_text, choice_text]))[:10]
    return {
        "prompt_ngrams": char_ngrams(prompt_compact, 3),
        "answer_ngrams": char_ngrams(answer_compact, 3),
        "choice_ngrams": char_ngrams(choice_compact, 3),
        "seed_terms": seed_terms,
        "cluster_tags": dedupe_preserve_order(topic_tags + adaptive_tags),
    }


def embedding_source_text(question: Dict[str, object], enrichment: Dict[str, object]) -> str:
    correct_text = " ".join(
        normalize_text(choice.get("text_ja") or choice.get("text") or "")
        for choice in question.get("choices", [])
        if choice.get("id") in question.get("correct_choice_ids", [])
    )
    choice_text = " ".join(
        normalize_text(choice.get("text_ja") or choice.get("text") or "")
        for choice in question.get("choices", [])
    )
    doc_basis = enrichment.get("doc_basis", {})
    basis_terms = doc_basis.get("basis_terms", []) if isinstance(doc_basis, dict) else []
    parts = [
        normalize_text(question.get("prompt_ja") or question.get("prompt") or ""),
        normalize_text(question.get("overall_explanation_ja") or question.get("overall_explanation") or ""),
        correct_text,
        choice_text,
        " ".join(enrichment.get("topic_tags", [])),
        " ".join(enrichment.get("adaptive_tags", [])),
        " ".join(enrichment.get("release_tags", [])),
        " ".join(basis_terms),
        normalize_text(enrichment.get("confusion_family_label") or ""),
    ]
    return " ".join(part for part in parts if part).strip()


def normalize_embedding_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


_SENTENCE_MODEL = None


def load_sentence_embedding_model():
    global _SENTENCE_MODEL
    if _SENTENCE_MODEL is not None:
        return _SENTENCE_MODEL
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        _SENTENCE_MODEL = False
        return None
    try:
        _SENTENCE_MODEL = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
    except Exception:
        _SENTENCE_MODEL = False
        return None
    return _SENTENCE_MODEL


def build_external_sentence_embeddings(
    bucket: Sequence[Dict[str, object]],
    enrichments: Dict[str, Dict[str, object]],
) -> Tuple[Optional[np.ndarray], Dict[str, object]]:
    model = load_sentence_embedding_model()
    if model is None:
        return None, {"provider": "unavailable", "model": DEFAULT_EMBEDDING_MODEL}

    texts = [embedding_source_text(question, enrichments[question["id"]]) for question in bucket]
    vectors = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    dense = np.asarray(vectors, dtype=float)
    if dense.ndim != 2 or dense.shape[0] != len(bucket):
        return None, {"provider": "failed", "model": DEFAULT_EMBEDDING_MODEL}
    return dense, {
        "provider": "sentence-transformers",
        "model": DEFAULT_EMBEDDING_MODEL,
        "dimensions": int(dense.shape[1]),
    }


def build_bucket_embeddings(
    bucket: Sequence[Dict[str, object]],
    enrichments: Dict[str, Dict[str, object]],
) -> Tuple[Dict[str, np.ndarray], Dict[str, object]]:
    if not bucket:
        return {}, {"method": "empty", "dimensions": 0, "variance_explained": 0.0}

    texts = [embedding_source_text(question, enrichments[question["id"]]) for question in bucket]
    if len(texts) == 1:
        return {bucket[0]["id"]: np.array([1.0], dtype=float)}, {
            "method": "singleton",
            "dimensions": 1,
            "variance_explained": 1.0,
        }

    word_vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=1,
        max_features=6000,
        sublinear_tf=True,
    )
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=1,
        max_features=12000,
        sublinear_tf=True,
    )
    word_matrix = word_vectorizer.fit_transform(texts)
    char_matrix = char_vectorizer.fit_transform(texts)
    feature_matrix = hstack([word_matrix, char_matrix], format="csr")

    max_components = min(96, feature_matrix.shape[0] - 1, feature_matrix.shape[1] - 1)
    if max_components >= 8:
        svd = TruncatedSVD(n_components=max_components, random_state=42)
        dense = svd.fit_transform(feature_matrix)
        explained = float(np.sum(svd.explained_variance_ratio_))
    else:
        dense = feature_matrix.toarray()
        explained = 1.0

    dense = normalize_embedding_rows(np.asarray(dense, dtype=float))
    external_dense, external_meta = build_external_sentence_embeddings(bucket, enrichments)
    method = "tfidf_word_char_svd_embedding"
    external_model = None
    external_provider = None
    if external_dense is not None:
        local_weight = 0.34
        external_weight = 0.66
        dense = np.concatenate([dense * local_weight, external_dense * external_weight], axis=1)
        dense = normalize_embedding_rows(dense)
        method = "sentence_transformer_plus_tfidf_svd_hybrid"
        external_model = external_meta.get("model")
        external_provider = external_meta.get("provider")
    vectors = {question["id"]: dense[index] for index, question in enumerate(bucket)}
    meta = {
        "method": method,
        "dimensions": int(dense.shape[1]),
        "variance_explained": round(explained, 4),
        "external_provider": external_provider,
        "external_model": external_model,
    }
    return vectors, meta


def cosine_similarity(left: Optional[np.ndarray], right: Optional[np.ndarray]) -> float:
    if left is None or right is None or left.size == 0 or right.size == 0:
        return 0.0
    return float(np.dot(left, right))


def build_doc_basis(
    question: Dict[str, object],
    concept_tags: List[str],
    release_tags: List[str],
    confusion_family: Optional[str],
) -> Dict[str, object]:
    links = docs_for_question(question)
    learn_more_topics = dedupe_preserve_order(
        [normalize_text(topic) for topic in question.get("learn_more_topics", []) if topic]
    )
    family_meta = CONFUSION_FAMILIES.get(confusion_family or "")
    if question.get("doc_urls"):
        basis_type = "official_url"
    elif learn_more_topics:
        basis_type = "learn_more_topic"
    elif family_meta:
        basis_type = "confusion_family"
    elif concept_tags:
        basis_type = "concept_tag"
    else:
        basis_type = "domain_fallback"

    primary_topic = (
        learn_more_topics[0]
        if learn_more_topics
        else (family_meta["doc_topics"][0] if family_meta else None)
    ) or (concept_label_ja(concept_tags[0]) if concept_tags else TOP_DOMAINS[question["top_domain"]]["label"])

    secondary_topics = dedupe_preserve_order(
        list(learn_more_topics[1:3])
        + (family_meta["doc_topics"][1:3] if family_meta else [])
        + [concept_label_ja(tag) for tag in concept_tags[:2]]
        + [current_service_label_ja(tag) for tag in release_tags[:2]]
    )
    secondary_topics = [topic for topic in secondary_topics if topic != primary_topic][:3]

    basis_seed = [primary_topic] + secondary_topics
    if family_meta:
        basis_seed.append(family_meta["label_ja"])
    basis_terms = dedupe_preserve_order(basis_seed)
    return {
        "basis_type": basis_type,
        "primary_topic": primary_topic,
        "secondary_topics": secondary_topics,
        "source_urls": links[:3],
        "basis_terms": basis_terms[:5],
    }


def build_root_snippet(
    question: Dict[str, object],
    concept_tags: List[str],
    release_tags: List[str],
    confusion_family: Optional[str],
) -> str:
    family_meta = CONFUSION_FAMILIES.get(confusion_family or "")
    snippet = ""
    if family_meta:
        snippet = family_meta["root_snippet"]
    elif concept_tags:
        snippet = CONCEPT_COACH_NOTES.get(concept_tags[0], "")
    if not snippet:
        snippet = DOMAIN_COACH_NOTES.get(question["top_domain"], "")
    if release_tags:
        release_focus = " / ".join(current_service_label_ja(tag) for tag in release_tags[:2])
        if release_focus:
            snippet = f"{snippet} 2026重点: {release_focus}。".strip()
    return snippet


def build_question_enrichment(question: Dict[str, object]) -> Dict[str, object]:
    topic_tags = extract_topic_tags(question)
    adaptive_tags = extract_adaptive_tags(question)
    release_tags = current_release_tags(adaptive_tags)
    confusion_family = detect_confusion_family(question, topic_tags, adaptive_tags)
    return {
        "topic_tags": topic_tags,
        "adaptive_tags": adaptive_tags,
        "release_tags": release_tags,
        "confusion_family": confusion_family,
        "confusion_family_label": CONFUSION_FAMILIES.get(confusion_family or "", {}).get("label_ja"),
        "doc_basis": build_doc_basis(question, adaptive_tags, release_tags, confusion_family),
        "root_snippet": build_root_snippet(question, adaptive_tags, release_tags, confusion_family),
        "similarity": question_similarity_meta(question, topic_tags, adaptive_tags),
    }


def build_exact_duplicate_metadata(questions: List[Dict[str, object]]) -> Tuple[Dict[str, Dict[str, object]], Dict[str, int]]:
    groups: Dict[str, List[Dict[str, object]]] = {}
    for question in questions:
        signature = question.get("signature") or question["id"]
        groups.setdefault(signature, []).append(question)

    metadata: Dict[str, Dict[str, object]] = {}
    duplicate_group_count = 0
    duplicate_question_count = 0
    largest_group = 1
    for signature, members in groups.items():
        ordered = sorted(members, key=lambda item: item["global_index"])
        group_size = len(ordered)
        if group_size > 1:
            duplicate_group_count += 1
            duplicate_question_count += group_size
        largest_group = max(largest_group, group_size)
        group_id = f"dup-{hashlib.sha1(str(signature).encode('utf-8')).hexdigest()[:10]}"
        anchor_id = ordered[0]["id"]
        for rank, question in enumerate(ordered, start=1):
            metadata[question["id"]] = {
                "duplicate_group_id": group_id,
                "duplicate_group_size": group_size,
                "duplicate_group_rank": rank,
                "duplicate_group_anchor_id": anchor_id,
                "exact_duplicate": group_size > 1,
            }
    summary = {
        "group_count": duplicate_group_count,
        "question_count": duplicate_question_count,
        "largest_group": largest_group,
    }
    return metadata, summary


def semantic_similarity_score(left: Dict[str, object], right: Dict[str, object]) -> float:
    left_similarity = left["similarity"]
    right_similarity = right["similarity"]
    prompt_score = jaccard_score(left_similarity["prompt_ngrams"], right_similarity["prompt_ngrams"])
    answer_score = jaccard_score(left_similarity["answer_ngrams"], right_similarity["answer_ngrams"])
    choice_score = jaccard_score(left_similarity["choice_ngrams"], right_similarity["choice_ngrams"])
    tag_score = jaccard_score(left_similarity["cluster_tags"], right_similarity["cluster_tags"])
    seed_score = jaccard_score(left_similarity["seed_terms"], right_similarity["seed_terms"])
    confusion_bonus = 0.08 if left.get("confusion_family") and left.get("confusion_family") == right.get("confusion_family") else 0.0
    embedding_score = 0.0
    if left.get("embedding_vector") is not None and right.get("embedding_vector") is not None:
        embedding_score = cosine_similarity(left["embedding_vector"], right["embedding_vector"])
    return min(
        1.0,
        prompt_score * 0.26
        + answer_score * 0.12
        + choice_score * 0.08
        + tag_score * 0.10
        + seed_score * 0.06
        + embedding_score * 0.38
        + confusion_bonus,
    )


def is_near_duplicate(left: Dict[str, object], right: Dict[str, object]) -> bool:
    if left.get("duplicate_group_id") == right.get("duplicate_group_id"):
        return True
    left_similarity = left["similarity"]
    right_similarity = right["similarity"]
    prompt_score = jaccard_score(left_similarity["prompt_ngrams"], right_similarity["prompt_ngrams"])
    answer_score = jaccard_score(left_similarity["answer_ngrams"], right_similarity["answer_ngrams"])
    choice_score = jaccard_score(left_similarity["choice_ngrams"], right_similarity["choice_ngrams"])
    tag_score = jaccard_score(left_similarity["cluster_tags"], right_similarity["cluster_tags"])
    seed_score = jaccard_score(left_similarity["seed_terms"], right_similarity["seed_terms"])
    embedding_score = 0.0
    if left.get("embedding_vector") is not None and right.get("embedding_vector") is not None:
        embedding_score = cosine_similarity(left["embedding_vector"], right["embedding_vector"])
    total_score = semantic_similarity_score(left, right)
    if embedding_score >= 0.965 and tag_score >= 0.12:
        return True
    if embedding_score >= 0.94 and (answer_score >= 0.22 or choice_score >= 0.30 or seed_score >= 0.24):
        return True
    if prompt_score >= 0.86 and (answer_score >= 0.20 or choice_score >= 0.32):
        return True
    if prompt_score >= 0.74 and answer_score >= 0.34 and (tag_score >= 0.20 or seed_score >= 0.20):
        return True
    return total_score >= 0.8 and (embedding_score >= 0.88 or answer_score >= 0.24 or choice_score >= 0.38 or tag_score >= 0.30)


def build_semantic_cluster_metadata(
    questions: List[Dict[str, object]],
    enrichments: Dict[str, Dict[str, object]],
) -> Tuple[Dict[str, Dict[str, object]], Dict[str, int]]:
    parent = {question["id"]: question["id"] for question in questions}

    def find(item_id: str) -> str:
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    def union(left_id: str, right_id: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            return
        if left_root > right_root:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root

    by_bucket: Dict[Tuple[str, int], List[Dict[str, object]]] = {}
    for question in questions:
        bucket_key = (question["top_domain"], int(question.get("choose_count", 1)))
        by_bucket.setdefault(bucket_key, []).append(question)

    embedding_metas: List[Dict[str, object]] = []
    for bucket in by_bucket.values():
        ordered = sorted(bucket, key=lambda item: item["global_index"])
        vectors, meta = build_bucket_embeddings(ordered, enrichments)
        embedding_metas.append(meta)
        for question in ordered:
            enrichments[question["id"]]["embedding_vector"] = vectors[question["id"]]
        for index, left_question in enumerate(ordered):
            left = enrichments[left_question["id"]]
            for right_question in ordered[index + 1 :]:
                right = enrichments[right_question["id"]]
                if left["duplicate_group_id"] == right["duplicate_group_id"]:
                    union(left_question["id"], right_question["id"])
                    continue
                shared_terms = set(left["similarity"]["seed_terms"][:6]) & set(right["similarity"]["seed_terms"][:6])
                shared_tags = set(left["topic_tags"] + left["adaptive_tags"]) & set(right["topic_tags"] + right["adaptive_tags"])
                same_family = left.get("confusion_family") and left.get("confusion_family") == right.get("confusion_family")
                if not shared_terms and not shared_tags and not same_family:
                    continue
                if is_near_duplicate(left, right):
                    union(left_question["id"], right_question["id"])

    clusters: Dict[str, List[Dict[str, object]]] = {}
    for question in sorted(questions, key=lambda item: item["global_index"]):
        clusters.setdefault(find(question["id"]), []).append(question)

    metadata: Dict[str, Dict[str, object]] = {}
    cluster_count = 0
    cluster_question_count = 0
    largest_cluster = 1
    for members in clusters.values():
        ordered = sorted(members, key=lambda item: item["global_index"])
        cluster_size = len(ordered)
        if cluster_size > 1:
            cluster_count += 1
            cluster_question_count += cluster_size
        largest_cluster = max(largest_cluster, cluster_size)
        cluster_seed = "|".join(question["id"] for question in ordered[:4])
        cluster_id = f"sem-{hashlib.sha1(cluster_seed.encode('utf-8')).hexdigest()[:10]}"
        anchor_id = ordered[0]["id"]
        anchor_enrichment = enrichments[anchor_id]
        for rank, question in enumerate(ordered, start=1):
            similarity_to_anchor = 1.0 if question["id"] == anchor_id else semantic_similarity_score(enrichments[question["id"]], anchor_enrichment)
            embedding_similarity_to_anchor = 1.0
            if question["id"] != anchor_id:
                embedding_similarity_to_anchor = cosine_similarity(
                    enrichments[question["id"]].get("embedding_vector"),
                    anchor_enrichment.get("embedding_vector"),
                )
            metadata[question["id"]] = {
                "semantic_cluster_id": cluster_id,
                "semantic_cluster_size": cluster_size,
                "semantic_cluster_rank": rank,
                "semantic_cluster_anchor_id": anchor_id,
                "semantic_similarity_to_anchor": round(similarity_to_anchor, 3),
                "embedding_similarity_to_anchor": round(float(embedding_similarity_to_anchor), 3),
            }
    embedding_meta = next(
        (meta for meta in reversed(embedding_metas) if meta.get("external_provider") or meta.get("method")),
        {},
    )
    summary = {
        "cluster_count": cluster_count,
        "question_count": cluster_question_count,
        "largest_cluster": largest_cluster,
        "embedding_method": embedding_meta.get("method", "unknown"),
        "embedding_dimensions": embedding_meta.get("dimensions", 0),
        "embedding_variance_explained": embedding_meta.get("variance_explained", 0.0),
        "external_provider": embedding_meta.get("external_provider"),
        "external_model": embedding_meta.get("external_model"),
    }
    return metadata, summary


def active_pool_score(question: Dict[str, object], item: Dict[str, object]) -> float:
    score = 38.0
    score += min(26.0, float(item["score"]) * 0.46)
    score += min(8.0, len(item["topic_tags"]) * 1.7)
    score += min(7.0, len(item["adaptive_tags"]) * 1.25)
    score += min(5.0, len(item["release_tags"]) * 2.2)
    if item.get("confusion_family"):
        score += 5.0
    if question.get("multi_select"):
        score += 2.5
    if question.get("source_status_correct") is False:
        score += 3.0
    if question["id"] != item.get("canonical_id"):
        score -= 2.5
    score -= min(12.0, max(0, int(item.get("duplicate_group_size", 1)) - 1) * 7.0)
    score -= min(8.0, max(0, int(item.get("semantic_cluster_size", 1)) - 1) * 1.8)
    return round(max(1.0, min(99.0, score)), 2)


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


def irt_seed_params(
    question: Dict[str, object],
    adaptive_tags: List[str],
    enrichment: Dict[str, object],
) -> Dict[str, float]:
    difficulty = base_difficulty_seed(question, adaptive_tags)
    discrimination = 1.0
    discrimination += 0.18 if question.get("multi_select") else 0.0
    discrimination += min(0.22, len(adaptive_tags) * 0.03)
    if enrichment.get("confusion_family"):
        discrimination += 0.14
    if question.get("source_status_correct") is False:
        discrimination += 0.08
    guess = 0.14 if int(question.get("choose_count", 1)) == 1 else 0.08
    return {
        "difficulty": round(max(0.2, min(0.95, difficulty)), 3),
        "discrimination": round(max(0.8, min(2.2, discrimination)), 3),
        "guess": round(max(0.02, min(0.2, guess)), 3),
    }


def narrow_scope_hits(question: Dict[str, object]) -> List[str]:
    blob = question_blob_ja(question)
    return [pattern for pattern in NARROW_SCOPE_PATTERNS if pattern in blob]


def curation_score(question: Dict[str, object], enrichment: Optional[Dict[str, object]] = None) -> Tuple[float, List[str], List[str]]:
    score = 0.0
    reasons: List[str] = []
    enrichment = enrichment or build_question_enrichment(question)

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

    topic_tags = list(enrichment.get("topic_tags", []))
    if topic_tags:
        score += min(12.0, len(topic_tags) * 3.0)
        reasons.append("コア論点: " + ", ".join(topic_tags[:3]))
    else:
        score -= 4.0

    release_tags = list(enrichment.get("release_tags", []))
    if release_tags:
        score += min(10.0, len(release_tags) * 4.0)
        reasons.append("2026現行トピック: " + ", ".join(release_tags[:2]))

    if enrichment.get("confusion_family"):
        score += 4.0
        reasons.append("混同しやすい概念セット")

    narrow_hits = narrow_scope_hits(question)
    if narrow_hits:
        score -= min(10.0, len(narrow_hits) * 4.0)

    return score, reasons[:4], topic_tags


def cluster_key(question: Dict[str, object], topic_tags: List[str], confusion_family: Optional[str] = None) -> str:
    correct_texts = [
        choice.get("text_ja", "")
        for choice in question.get("choices", [])
        if choice.get("id") in question.get("correct_choice_ids", [])
    ]
    answer_key = normalize_key(" | ".join(correct_texts))[:120]
    tag_key = "|".join(sorted(topic_tags)[:3])
    confusion_key = confusion_family or "-"
    return f"{question['top_domain']}|{confusion_key}|{tag_key}|{answer_key}"


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
    bounds = active_pool_bounds(count)
    enrichments = {question["id"]: build_question_enrichment(question) for question in payload["questions"]}
    exact_duplicate_meta, exact_duplicate_summary = build_exact_duplicate_metadata(payload["questions"])
    for question_id, metadata in exact_duplicate_meta.items():
        enrichments[question_id].update(metadata)
    semantic_cluster_meta, semantic_cluster_summary = build_semantic_cluster_metadata(payload["questions"], enrichments)
    for question_id, metadata in semantic_cluster_meta.items():
        enrichments[question_id].update(metadata)

    scored = []
    for question in payload["questions"]:
        enrichment = enrichments[question["id"]]
        score, reasons, topic_tags = curation_score(question, enrichment)
        adaptive_tags = list(enrichment["adaptive_tags"])
        release_tags = list(enrichment["release_tags"])
        current_relevance_score = round(min(1.0, 0.22 + len(release_tags) * 0.22), 2)
        irt_seed = irt_seed_params(question, adaptive_tags, enrichment)
        scored.append(
            {
                "question": question,
                "score": score,
                "reasons": reasons,
                "topic_tags": topic_tags,
                "adaptive_tags": adaptive_tags,
                "release_tags": release_tags,
                "confusion_family": enrichment.get("confusion_family"),
                "confusion_family_label": enrichment.get("confusion_family_label"),
                "doc_basis": enrichment["doc_basis"],
                "root_snippet": enrichment["root_snippet"],
                "current_relevance_score": current_relevance_score,
                "base_difficulty": base_difficulty_seed(question, adaptive_tags),
                "irt_difficulty": irt_seed["difficulty"],
                "irt_discrimination": irt_seed["discrimination"],
                "irt_guess": irt_seed["guess"],
                "cluster_key": cluster_key(question, topic_tags, enrichment.get("confusion_family")),
                "duplicate_group_id": enrichment["duplicate_group_id"],
                "duplicate_group_size": enrichment["duplicate_group_size"],
                "duplicate_group_rank": enrichment["duplicate_group_rank"],
                "duplicate_group_anchor_id": enrichment["duplicate_group_anchor_id"],
                "semantic_cluster_id": enrichment["semantic_cluster_id"],
                "semantic_cluster_size": enrichment["semantic_cluster_size"],
                "semantic_cluster_rank": enrichment["semantic_cluster_rank"],
                "semantic_cluster_anchor_id": enrichment["semantic_cluster_anchor_id"],
                "semantic_similarity_to_anchor": enrichment["semantic_similarity_to_anchor"],
                "embedding_similarity_to_anchor": enrichment.get("embedding_similarity_to_anchor", enrichment["semantic_similarity_to_anchor"]),
            }
        )

    ranking_order = sorted(
        scored,
        key=lambda item: (-item["score"], -item["question"]["source_set"], item["question"]["global_index"]),
    )
    semantic_canonical: Dict[str, str] = {}
    duplicate_canonical: Dict[str, str] = {}
    for item in ranking_order:
        semantic_canonical.setdefault(item["semantic_cluster_id"], item["question"]["id"])
        duplicate_canonical.setdefault(item["duplicate_group_id"], item["question"]["id"])
    for item in scored:
        item["canonical_id"] = semantic_canonical[item["semantic_cluster_id"]]
        item["duplicate_canonical_id"] = duplicate_canonical[item["duplicate_group_id"]]
        item["active_pool_score"] = active_pool_score(item["question"], item)

    by_domain: Dict[str, List[Dict[str, object]]] = {key: [] for key in TOP_DOMAINS}
    for item in scored:
        by_domain[item["question"]["top_domain"]].append(item)
    for domain_key in by_domain:
        by_domain[domain_key].sort(
            key=lambda item: (
                -item["active_pool_score"],
                -item["score"],
                -item["question"]["source_set"],
                item["question"]["global_index"],
            )
        )

    selected: List[Dict[str, object]] = []
    selected_ids = set()
    selected_duplicate_groups = set()
    domain_counts = {key: 0 for key in TOP_DOMAINS}
    cluster_counts: Dict[str, int] = {}
    semantic_cluster_counts: Dict[str, int] = {}

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
                if item["duplicate_group_id"] in selected_duplicate_groups:
                    continue
                current_semantic_cluster_count = semantic_cluster_counts.get(item["semantic_cluster_id"], 0)
                if current_semantic_cluster_count >= cluster_cap:
                    continue
                current_cluster_count = cluster_counts.get(item["cluster_key"], 0)
                if current_cluster_count >= cluster_cap:
                    continue
                cluster_counts[item["cluster_key"]] = current_cluster_count + 1
                semantic_cluster_counts[item["semantic_cluster_id"]] = current_semantic_cluster_count + 1
                domain_counts[domain_key] += 1
                selected_ids.add(question["id"])
                selected_duplicate_groups.add(item["duplicate_group_id"])
                selected.append(item)

    active_ranked = sorted(
        selected,
        key=lambda item: (-item["active_pool_score"], -item["score"], item["question"]["global_index"]),
    )
    active_rank_lookup: Dict[str, int] = {}
    active_band_lookup: Dict[str, str] = {}
    for rank, item in enumerate(active_ranked, start=1):
        active_rank_lookup[item["question"]["id"]] = rank
        if rank <= bounds["min_size"]:
            band = "foundation"
        elif rank <= bounds["default_size"]:
            band = "core"
        elif rank <= bounds["max_size"]:
            band = "stretch"
        else:
            band = "reserve"
        active_band_lookup[item["question"]["id"]] = band

    selected_questions = []
    live_doc_cache: Dict[str, Dict[str, object]] = {}
    live_doc_hits = 0
    for curated_index, item in enumerate(selected, start=1):
        question = item["question"]
        explanation = build_explanation_ja(question, item["adaptive_tags"], item["release_tags"])
        question_like = {
            "id": question["id"],
            "domain_key": question["top_domain"],
            "doc_basis": item["doc_basis"],
            "current_service_tags": item["release_tags"],
            "confusion_family": item["confusion_family"],
        }
        official_doc_evidence = resolve_official_doc_evidence(question_like, memory_cache=live_doc_cache)
        if official_doc_evidence:
            live_doc_hits += 1
        docs_links = dedupe_preserve_order(
            ([official_doc_evidence["url"]] if official_doc_evidence and official_doc_evidence.get("url") else [])
            + docs_for_question(question)
        )
        selected_questions.append(
            {
                "curated_index": curated_index,
                "id": question["id"],
                "canonical_id": item["canonical_id"],
                "duplicate_group_id": item["duplicate_group_id"],
                "duplicate_group_size": item["duplicate_group_size"],
                "semantic_cluster_id": item["semantic_cluster_id"],
                "semantic_cluster_size": item["semantic_cluster_size"],
                "semantic_similarity_to_anchor": item["semantic_similarity_to_anchor"],
                "embedding_similarity_to_anchor": item["embedding_similarity_to_anchor"],
                "confusion_family": item["confusion_family"],
                "confusion_family_label": item["confusion_family_label"],
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
                "explanation": explanation,
                "original_explanation": question["overall_explanation"],
                "root_snippet": item["root_snippet"],
                "doc_basis": item["doc_basis"],
                "docs": docs_links,
                "official_doc_evidence": official_doc_evidence,
                "yield_score": round(item["score"], 2),
                "yield_reasons": item["reasons"],
                "topic_tags": item["topic_tags"],
                "concept_tags": item["adaptive_tags"],
                "current_service_tags": item["release_tags"],
                "current_relevance_score": item["current_relevance_score"],
                "delta_relevance_score": round(min(0.15, 0.05 + len(item["release_tags"]) * 0.05), 3),
                "base_difficulty": item["base_difficulty"],
                "irt_difficulty": item["irt_difficulty"],
                "irt_discrimination": item["irt_discrimination"],
                "irt_guess": item["irt_guess"],
                "exam_weight": TOP_DOMAINS[question["top_domain"]]["weight"],
                "active_pool_score": item["active_pool_score"],
                "active_pool_rank": active_rank_lookup[question["id"]],
                "active_pool_band": active_band_lookup[question["id"]],
                "default_active": active_rank_lookup[question["id"]] <= bounds["default_size"],
                "delta_mode": {
                    "enabled": True,
                    "release_tags": item["release_tags"],
                    "relevance_score": round(min(0.15, 0.05 + len(item["release_tags"]) * 0.05), 3),
                    "weight_fraction_cap": 0.15,
                },
                "shadow_log_context": {
                    "question_id": question["id"],
                    "canonical_id": item["canonical_id"],
                    "duplicate_group_id": item["duplicate_group_id"],
                    "semantic_cluster_id": item["semantic_cluster_id"],
                    "domain_key": question["top_domain"],
                    "topic_tags": item["topic_tags"],
                    "concept_tags": item["adaptive_tags"],
                    "current_service_tags": item["release_tags"],
                    "confusion_family": item["confusion_family"],
                    "base_difficulty": item["base_difficulty"],
                    "irt_difficulty": item["irt_difficulty"],
                    "irt_discrimination": item["irt_discrimination"],
                    "active_pool_score": item["active_pool_score"],
                    "active_pool_rank": active_rank_lookup[question["id"]],
                },
                "source_set": question["source_set"],
                "source_number": question["source_number"],
                "source_status_correct": question["source_status_correct"],
            }
        )

    shadow_promotion = load_shadow_promotion()
    shadow_runtime = shadow_promotion.get("question_runtime", {}) if isinstance(shadow_promotion, dict) else {}
    for question in selected_questions:
        if question["id"] in shadow_runtime:
            question["shadow_runtime"] = shadow_runtime[question["id"]]

    confusion_counts_raw: Dict[str, int] = {}
    confusion_counts_curated: Dict[str, int] = {}
    for item in scored:
        if item.get("confusion_family"):
            confusion_counts_raw[item["confusion_family"]] = confusion_counts_raw.get(item["confusion_family"], 0) + 1
    for question in selected_questions:
        if question.get("confusion_family"):
            confusion_counts_curated[question["confusion_family"]] = confusion_counts_curated.get(question["confusion_family"], 0) + 1

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
                "active_pool_targets": {
                    "min_size": domain_targets(bounds["min_size"])[domain_key],
                    "default_size": domain_targets(bounds["default_size"])[domain_key],
                    "max_size": domain_targets(bounds["max_size"])[domain_key],
                },
                "active_pool_actual": {
                    "min_size": sum(1 for question in picked if question["active_pool_rank"] <= bounds["min_size"]),
                    "default_size": sum(1 for question in picked if question["active_pool_rank"] <= bounds["default_size"]),
                    "max_size": sum(1 for question in picked if question["active_pool_rank"] <= bounds["max_size"]),
                },
            }
        )

    plan = study_plan(selected_questions, days=days, daily_hours=daily_hours)
    return {
        "built_at": iso_now(),
        "source": sanitize_source_label(payload["source"]),
        "selection_policy": [
            "2026年1月更新の公式CSAブループリント配分で600問に圧縮",
            "高品質バンク・学習領域メタデータ・解説の厚さを優先",
            "署名ベース完全重複は1代表に抑え、TF-IDF + SVD 埋め込みで意味近似クラスタを作る",
            "混同しやすい概念セットと2026年4月時点の現行ServiceNow文脈に追加加点",
            "公式Docs根拠は ServiceNow Fluid Topics の live 検索APIで更新し、静的メタ情報だけに依存しない",
            "600問は上限プールとし、実運用のアクティブ学習セットは420〜560問、初期推奨は480問",
            "2週間・1日2-3時間で回せるよう、複数選択と弱点化しやすい論点を少し厚めに採用",
        ],
        "official_context": OFFICIAL_EXAM_CONTEXT,
        "delta_mode": {
            "enabled": True,
            "label": "CSA 2026 Delta Mode",
            "release_family": OFFICIAL_EXAM_CONTEXT["current_release_family"],
            "release_updated": OFFICIAL_EXAM_CONTEXT["current_release_updated"],
            "exam_blueprint_updated": OFFICIAL_EXAM_CONTEXT["exam_blueprint_updated"],
            "focus_tags": OFFICIAL_EXAM_CONTEXT["exam_priority_topics"],
            "weight_fraction_cap": 0.15,
        },
        "shadow_log_schema": {
            "version": 1,
            "question_context_fields": [
                "question_id",
                "canonical_id",
                "duplicate_group_id",
                "semantic_cluster_id",
                "domain_key",
                "topic_tags",
                "concept_tags",
                "current_service_tags",
                "confusion_family",
                "base_difficulty",
                "irt_difficulty",
                "irt_discrimination",
                "active_pool_score",
                "active_pool_rank",
            ],
            "attempt_event_fields": [
                "question_id",
                "presented_at",
                "submitted_at",
                "selected_choice_ids",
                "is_correct",
                "hint_count",
                "predicted_recall_before",
                "predicted_recall_after",
                "knowledge_prob_before",
                "knowledge_prob_after",
                "bandit_reward",
                "working_set_size",
                "question_source",
            ],
        },
        "shadow_model": (
            {
                "generated_at": shadow_promotion.get("generated_at"),
                "promoted": bool(shadow_promotion.get("promoted")),
                "promotion_reason": shadow_promotion.get("promotion_reason"),
                "active_model": shadow_promotion.get("active_model"),
                "baseline_model": shadow_promotion.get("baseline_model"),
                "champion_model": shadow_promotion.get("champion_model"),
                "valid_examples": shadow_promotion.get("valid_examples"),
                "metrics": shadow_promotion.get("metrics"),
            }
            if isinstance(shadow_promotion, dict)
            else {
                "generated_at": None,
                "promoted": False,
                "promotion_reason": "shadow training 未実行",
                "active_model": "baseline",
                "baseline_model": "baseline",
                "champion_model": "baseline",
                "valid_examples": 0,
                "metrics": None,
            }
        ),
        "meta": {
            "curated_count": len(selected_questions),
            "curated_cap": count,
            "full_question_count": payload["question_count"],
            "study_days": days,
            "daily_hours": daily_hours,
            "active_pool_bounds": bounds,
            "duplicate_summary": {
                "exact": exact_duplicate_summary,
                "semantic": semantic_cluster_summary,
            },
            "confusion_family_counts_raw": confusion_counts_raw,
            "confusion_family_counts_curated": confusion_counts_curated,
            "official_doc_live": {
                "provider": "servicenow-fluidtopics-live",
                "cache_ttl_hours": OFFICIAL_DOCS_CACHE_TTL_HOURS,
                "questions_with_live_evidence": live_doc_hits,
                "unique_queries_resolved": len(live_doc_cache),
                "search_api": OFFICIAL_DOCS_SEARCH_API,
            },
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


def load_shadow_promotion() -> Optional[Dict[str, object]]:
    if not SHADOW_PROMOTION_PATH.exists():
        return None
    try:
        payload = json.loads(SHADOW_PROMOTION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def export_web_data(curated: Dict[str, object]) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DATA_PATH.write_text(json.dumps(curated, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def shadow_question_id(event: Dict[str, object]) -> Optional[str]:
    return event.get("questionId") or event.get("question_id")


def load_shadow_events(paths: Sequence[Path]) -> List[Dict[str, object]]:
    events: List[Dict[str, object]] = []
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Shadow log not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            events.append(entry)
    events.sort(key=lambda item: item.get("submittedAt") or item.get("at") or "")
    return events


def build_shadow_attempts(events: Sequence[Dict[str, object]], curated: Dict[str, object]) -> List[Dict[str, object]]:
    question_lookup = {question["id"]: question for question in curated["questions"]}
    attempts: List[Dict[str, object]] = []
    for event in events:
        if event.get("type") != "drill_answer_recorded":
            continue
        question_id = shadow_question_id(event)
        if not question_id or question_id not in question_lookup:
            continue
        question = question_lookup[question_id]
        timestamp = event.get("submittedAt") or event.get("at")
        if not timestamp:
            continue
        attempts.append(
            {
                "question_id": question_id,
                "question_index": question["curated_index"] - 1,
                "correct": 1 if event.get("correct") else 0,
                "hints_used": int(event.get("hintsUsed") or 0),
                "timestamp": timestamp,
                "domain_key": question["domain_key"],
                "confusion_family": question.get("confusion_family"),
            }
        )
    attempts.sort(key=lambda item: item["timestamp"])
    return attempts


def segment_shadow_sequences(attempts: Sequence[Dict[str, object]], gap_hours: float = 6.0) -> List[List[Dict[str, object]]]:
    sequences: List[List[Dict[str, object]]] = []
    current: List[Dict[str, object]] = []
    previous_at: Optional[datetime] = None
    for attempt in attempts:
        current_at = datetime.fromisoformat(str(attempt["timestamp"]).replace("Z", "+00:00"))
        if previous_at is not None:
            gap = (current_at - previous_at).total_seconds() / 3600
            if gap > gap_hours and current:
                if len(current) >= 3:
                    sequences.append(current)
                current = []
        current.append(attempt)
        previous_at = current_at
    if len(current) >= 3:
        sequences.append(current)
    return sequences


def sliding_windows(sequence: Sequence[Dict[str, object]], window: int) -> List[List[Dict[str, object]]]:
    length = len(sequence)
    if length < 3:
        return []
    if length <= window:
        min_chunk = min(length, max(4, min(window, 6)))
        step = 1 if length <= 8 else 2
        windows: List[List[Dict[str, object]]] = []
        for end in range(min_chunk, length + 1, step):
            chunk = list(sequence[:end])
            if len(chunk) >= 3:
                windows.append(chunk)
        full = list(sequence)
        if not windows or windows[-1] != full:
            windows.append(full)
        return windows
    stride = max(1, window // 3)
    windows: List[List[Dict[str, object]]] = []
    for start in range(0, length - 1, stride):
        chunk = list(sequence[start : start + window])
        if len(chunk) >= 3:
            windows.append(chunk)
        if start + window >= length:
            break
    tail = list(sequence[-window:])
    if len(tail) >= 3 and (not windows or windows[-1] != tail):
        windows.append(tail)
    return windows


def split_shadow_sequences(sequences: Sequence[List[Dict[str, object]]]) -> Tuple[List[List[Dict[str, object]]], List[List[Dict[str, object]]]]:
    if len(sequences) <= 1:
        return list(sequences), list(sequences)
    cut = max(1, math.floor(len(sequences) * 0.8))
    train = list(sequences[:cut])
    valid = list(sequences[cut:]) or list(sequences[-1:])
    return train, valid


def sequence_examples(sequences: Sequence[List[Dict[str, object]]], window: int) -> List[Dict[str, object]]:
    examples: List[Dict[str, object]] = []
    for sequence in sequences:
        for chunk in sliding_windows(sequence, window):
            question_ids = [attempt["question_index"] for attempt in chunk]
            responses = [attempt["correct"] for attempt in chunk]
            examples.append(
                {
                    "input_question_ids": question_ids[:-1],
                    "input_responses": responses[:-1],
                    "target_question_ids": question_ids[1:],
                    "target_responses": responses[1:],
                }
            )
    return examples


def split_shadow_examples(
    examples: Sequence[Dict[str, object]],
    *,
    min_valid_examples: int = 6,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    ordered = list(examples)
    if len(ordered) <= 3:
        return ordered, ordered
    valid_count = max(min_valid_examples, math.ceil(len(ordered) * 0.2))
    valid_count = min(valid_count, len(ordered) - 2)
    valid_count = max(2, valid_count)
    cut = max(1, len(ordered) - valid_count)
    return ordered[:cut], ordered[cut:]


def batch_examples(examples: Sequence[Dict[str, object]], batch_size: int) -> List[List[Dict[str, object]]]:
    return [list(examples[index : index + batch_size]) for index in range(0, len(examples), batch_size)]


def tensorize_batch(batch: Sequence[Dict[str, object]], num_questions: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    max_len = max(len(example["input_question_ids"]) for example in batch)
    interaction = torch.zeros((len(batch), max_len), dtype=torch.long)
    input_q = torch.zeros((len(batch), max_len), dtype=torch.long)
    target_q = torch.zeros((len(batch), max_len), dtype=torch.long)
    target_y = torch.zeros((len(batch), max_len), dtype=torch.float32)
    mask = torch.zeros((len(batch), max_len), dtype=torch.float32)
    for row, example in enumerate(batch):
        length = len(example["input_question_ids"])
        for col in range(length):
            qid = int(example["input_question_ids"][col])
            resp = int(example["input_responses"][col])
            interaction[row, col] = qid + 1 + resp * num_questions
            input_q[row, col] = qid + 1
            target_q[row, col] = int(example["target_question_ids"][col]) + 1
            target_y[row, col] = float(example["target_responses"][col])
            mask[row, col] = 1.0
    return interaction, input_q, target_q, target_y * mask, mask


class ShadowDKTModel(torch.nn.Module):
    def __init__(self, num_questions: int, hidden_size: int) -> None:
        super().__init__()
        self.embedding = torch.nn.Embedding(num_questions * 2 + 1, hidden_size)
        self.gru = torch.nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.output = torch.nn.Linear(hidden_size, num_questions + 1)

    def forward(self, interaction: torch.Tensor) -> torch.Tensor:
        encoded = self.embedding(interaction)
        hidden, _ = self.gru(encoded)
        return self.output(hidden)


class ShadowSAKTModel(torch.nn.Module):
    def __init__(self, num_questions: int, hidden_size: int, heads: int = 4) -> None:
        super().__init__()
        self.interaction_embedding = torch.nn.Embedding(num_questions * 2 + 1, hidden_size)
        self.question_embedding = torch.nn.Embedding(num_questions + 1, hidden_size)
        self.attention = torch.nn.MultiheadAttention(hidden_size, heads, dropout=0.1, batch_first=True)
        self.norm = torch.nn.LayerNorm(hidden_size)
        self.ff = torch.nn.Sequential(
            torch.nn.Linear(hidden_size, hidden_size),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.1),
            torch.nn.Linear(hidden_size, hidden_size),
        )
        self.output = torch.nn.Linear(hidden_size, 1)

    def forward(self, interaction: torch.Tensor, target_q: torch.Tensor, *, full_context: bool = False) -> torch.Tensor:
        memory = self.interaction_embedding(interaction)
        query = self.question_embedding(target_q)
        seq_len = interaction.size(1)
        target_len = target_q.size(1)
        causal_mask = None
        if not full_context:
            causal_mask = torch.triu(
                torch.ones((target_len, seq_len), device=interaction.device, dtype=torch.bool),
                diagonal=1,
            )
        attended, _ = self.attention(query, memory, memory, attn_mask=causal_mask)
        hidden = self.norm(attended + self.ff(attended))
        return self.output(hidden).squeeze(-1)


def metric_summary(targets: Sequence[float], probs: Sequence[float]) -> Dict[str, object]:
    if not targets:
        return {"accuracy": 0.0, "brier": 0.0, "log_loss": 0.0, "auc": None}
    y_true = np.asarray(targets, dtype=float)
    y_prob = np.clip(np.asarray(probs, dtype=float), 1e-5, 1 - 1e-5)
    y_pred = (y_prob >= 0.5).astype(int)
    auc: Optional[float]
    if len(set(y_true.tolist())) < 2:
        auc = None
    else:
        auc = float(roc_auc_score(y_true, y_prob))
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "brier": round(float(brier_score_loss(y_true, y_prob)), 4),
        "log_loss": round(float(log_loss(y_true, y_prob, labels=[0.0, 1.0])), 4),
        "auc": round(auc, 4) if auc is not None else None,
    }


def baseline_shadow_predictions(
    train_sequences: Sequence[List[Dict[str, object]]],
    valid_sequences: Sequence[List[Dict[str, object]]],
) -> Dict[str, object]:
    question_stats: Dict[int, List[int]] = {}
    domain_stats: Dict[str, List[int]] = {}
    global_results: List[int] = []
    for sequence in train_sequences:
        for attempt in sequence:
            question_stats.setdefault(attempt["question_index"], []).append(attempt["correct"])
            domain_stats.setdefault(attempt["domain_key"], []).append(attempt["correct"])
            global_results.append(attempt["correct"])

    global_mean = (sum(global_results) + 1.0) / (len(global_results) + 2.0) if global_results else 0.58
    targets: List[float] = []
    probs: List[float] = []
    for sequence in valid_sequences:
        for attempt in sequence[1:]:
            q_values = question_stats.get(attempt["question_index"], [])
            d_values = domain_stats.get(attempt["domain_key"], [])
            q_mean = (sum(q_values) + 1.0) / (len(q_values) + 2.0) if q_values else global_mean
            d_mean = (sum(d_values) + 1.0) / (len(d_values) + 2.0) if d_values else global_mean
            prob = q_mean * 0.44 + d_mean * 0.32 + global_mean * 0.24
            targets.append(float(attempt["correct"]))
            probs.append(prob)
    return {
        "model": "baseline",
        "metrics": metric_summary(targets, probs),
    }


def train_shadow_model(
    model_kind: str,
    train_examples: Sequence[Dict[str, object]],
    valid_examples: Sequence[Dict[str, object]],
    num_questions: int,
    epochs: int,
    hidden_size: int,
    batch_size: int,
) -> Dict[str, object]:
    torch.manual_seed(42)
    if model_kind == "dkt":
        model: torch.nn.Module = ShadowDKTModel(num_questions, hidden_size)
    elif model_kind == "sakt":
        model = ShadowSAKTModel(num_questions, hidden_size)
    else:
        raise SystemExit(f"Unsupported shadow model: {model_kind}")

    optimizer = torch.optim.Adam(model.parameters(), lr=0.004)
    criterion = torch.nn.BCEWithLogitsLoss(reduction="none")

    def run_epoch(examples: Sequence[Dict[str, object]], train_mode: bool) -> Tuple[float, List[float], List[float]]:
        total_loss = 0.0
        total_weight = 0.0
        all_targets: List[float] = []
        all_probs: List[float] = []
        model.train(train_mode)
        for batch in batch_examples(examples, batch_size):
            interaction, _input_q, target_q, target_y, mask = tensorize_batch(batch, num_questions)
            if model_kind == "dkt":
                logits_all = model(interaction)
                gathered = torch.gather(logits_all, 2, target_q.unsqueeze(-1)).squeeze(-1)
            else:
                gathered = model(interaction, target_q)
            loss = criterion(gathered, target_y) * mask
            denom = torch.clamp(mask.sum(), min=1.0)
            batch_loss = loss.sum() / denom
            if train_mode:
                optimizer.zero_grad()
                batch_loss.backward()
                optimizer.step()
            total_loss += float(loss.sum().item())
            total_weight += float(mask.sum().item())
            probs = torch.sigmoid(gathered).detach().cpu().numpy()
            targets = target_y.detach().cpu().numpy()
            mask_np = mask.detach().cpu().numpy()
            for index in range(mask_np.shape[0]):
                for col in range(mask_np.shape[1]):
                    if mask_np[index, col] > 0:
                        all_targets.append(float(targets[index, col]))
                        all_probs.append(float(probs[index, col]))
        return (total_loss / total_weight if total_weight else 0.0), all_targets, all_probs

    best_snapshot: Optional[Dict[str, object]] = None
    history: List[Dict[str, float]] = []
    for epoch in range(epochs):
        train_loss, _, _ = run_epoch(train_examples, train_mode=True)
        valid_loss, valid_targets, valid_probs = run_epoch(valid_examples, train_mode=False)
        metrics = metric_summary(valid_targets, valid_probs)
        history.append({"epoch": epoch + 1, "train_loss": round(train_loss, 4), "valid_loss": round(valid_loss, 4)})
        score = metrics["auc"] if metrics["auc"] is not None else -metrics["log_loss"]
        if best_snapshot is None or score > best_snapshot["selection_score"]:
            best_snapshot = {
                "selection_score": score,
                "metrics": metrics,
                "history": list(history),
                "state_dict": {key: value.detach().cpu().clone() for key, value in model.state_dict().items()},
            }

    if best_snapshot is None:
        best_snapshot = {
            "selection_score": 0.0,
            "metrics": {"accuracy": 0.0, "brier": 0.0, "log_loss": 0.0, "auc": None},
            "history": history,
            "state_dict": {key: value.detach().cpu().clone() for key, value in model.state_dict().items()},
        }
    return {
        "model": model_kind,
        "metrics": best_snapshot["metrics"],
        "history": best_snapshot["history"][-5:],
        "hidden_size": hidden_size,
        "state_dict": best_snapshot["state_dict"],
    }


def instantiate_shadow_model(model_kind: str, num_questions: int, hidden_size: int) -> torch.nn.Module:
    if model_kind == "dkt":
        return ShadowDKTModel(num_questions, hidden_size)
    if model_kind == "sakt":
        return ShadowSAKTModel(num_questions, hidden_size)
    raise SystemExit(f"Unsupported shadow model: {model_kind}")


def load_trained_shadow_model(model_result: Dict[str, object], num_questions: int) -> torch.nn.Module:
    model = instantiate_shadow_model(str(model_result["model"]), num_questions, int(model_result["hidden_size"]))
    model.load_state_dict(model_result["state_dict"])
    model.eval()
    return model


def latest_shadow_context(attempts: Sequence[Dict[str, object]], window: int) -> List[Dict[str, object]]:
    if not attempts:
        return []
    return list(attempts[-max(1, window) :])


def predict_shadow_probabilities(
    model_result: Dict[str, object],
    attempts: Sequence[Dict[str, object]],
    num_questions: int,
    window: int,
) -> List[float]:
    context = latest_shadow_context(attempts, window)
    if not context:
        return [0.58] * num_questions
    model = load_trained_shadow_model(model_result, num_questions)
    interaction = torch.zeros((1, len(context)), dtype=torch.long)
    for col, attempt in enumerate(context):
        qid = int(attempt["question_index"])
        resp = int(attempt["correct"])
        interaction[0, col] = qid + 1 + resp * num_questions
    with torch.no_grad():
        if model_result["model"] == "dkt":
            logits_all = model(interaction)
            logits = logits_all[0, -1, 1 : num_questions + 1]
            probs = torch.sigmoid(logits).cpu().numpy().tolist()
        else:
            target_q = torch.arange(1, num_questions + 1, dtype=torch.long).unsqueeze(0)
            logits = model(interaction, target_q, full_context=True)[0]
            probs = torch.sigmoid(logits).cpu().numpy().tolist()
    return [float(max(0.03, min(0.99, prob))) for prob in probs]


def shadow_model_should_promote(champion: Dict[str, object], baseline: Dict[str, object], valid_examples: int) -> Tuple[bool, str]:
    if champion["model"] == "baseline":
        return False, "champion が baseline のまま"
    if valid_examples < 6:
        return False, "validation 例が少なすぎる"
    base_auc = baseline["metrics"]["auc"] or 0.0
    champ_auc = champion["metrics"]["auc"] or 0.0
    base_log = baseline["metrics"]["log_loss"]
    champ_log = champion["metrics"]["log_loss"]
    base_brier = baseline["metrics"]["brier"]
    champ_brier = champion["metrics"]["brier"]
    if champ_auc >= base_auc + 0.02 and champ_brier <= base_brier + 0.01:
        return True, "AUC と Brier で baseline を上回った"
    if champ_log <= base_log * 0.97 and champ_brier <= base_brier + 0.01:
        return True, "log loss で baseline を明確に改善した"
    return False, "baseline 超えが統計的に弱い"


def build_shadow_promotion(
    curated: Dict[str, object],
    attempts: Sequence[Dict[str, object]],
    baseline: Dict[str, object],
    champion: Dict[str, object],
    valid_examples: int,
    window: int,
) -> Dict[str, object]:
    num_questions = len(curated["questions"])
    promoted, reason = shadow_model_should_promote(champion, baseline, valid_examples)
    active_model = champion if promoted else baseline
    question_probs = (
        predict_shadow_probabilities(active_model, attempts, num_questions, window)
        if active_model["model"] != "baseline"
        else None
    )
    if question_probs is None:
        support_by_q: Dict[str, int] = {}
        success_by_q: Dict[str, int] = {}
        for attempt in attempts:
            question = curated["questions"][int(attempt["question_index"])]
            support_by_q[question["id"]] = support_by_q.get(question["id"], 0) + 1
            success_by_q[question["id"]] = success_by_q.get(question["id"], 0) + int(attempt["correct"])
        question_probs = []
        for question in curated["questions"]:
            support = support_by_q.get(question["id"], 0)
            success = success_by_q.get(question["id"], 0)
            prob = (success + 1.0) / (support + 2.0) if support else 0.58
            question_probs.append(float(prob))

    support_counts: Dict[str, int] = {}
    for attempt in attempts:
        question = curated["questions"][int(attempt["question_index"])]
        support_counts[question["id"]] = support_counts.get(question["id"], 0) + 1

    question_runtime: Dict[str, Dict[str, object]] = {}
    for question in curated["questions"]:
        prob = question_probs[question["curated_index"] - 1]
        support = support_counts.get(question["id"], 0)
        uncertainty = 1 / math.sqrt(support + 1)
        opportunity = max(0.0, min(1.35, 1 - abs(prob - 0.62) / 0.62 + uncertainty * 0.22 + (1 - prob) * 0.12))
        question_runtime[question["id"]] = {
            "model": active_model["model"],
            "predicted_success": round(prob, 4),
            "uncertainty": round(uncertainty, 4),
            "opportunity": round(float(opportunity), 4),
            "support": support,
            "promoted": promoted,
        }

    return {
        "generated_at": iso_now(),
        "promoted": promoted,
        "promotion_reason": reason,
        "active_model": active_model["model"],
        "baseline_model": baseline["model"],
        "champion_model": champion["model"],
        "valid_examples": valid_examples,
        "question_runtime": question_runtime,
        "metrics": {
            "baseline": baseline["metrics"],
            "champion": champion["metrics"],
        },
    }


def run_shadow_training(
    curated: Dict[str, object],
    log_paths: Sequence[Path],
    epochs: int,
    hidden_size: int,
    window: int,
    batch_size: int,
) -> Dict[str, object]:
    events = load_shadow_events(log_paths)
    attempts = build_shadow_attempts(events, curated)
    sequences = segment_shadow_sequences(attempts)
    train_sequences, valid_sequences = split_shadow_sequences(sequences)
    train_examples = sequence_examples(train_sequences, window)
    valid_examples = sequence_examples(valid_sequences, window)
    split_strategy = "sequence_holdout"
    if len(valid_examples) < 6:
        all_examples = sequence_examples(sequences, window)
        train_examples, valid_examples = split_shadow_examples(all_examples, min_valid_examples=6)
        split_strategy = "example_holdout_fallback"
    if not train_examples or not valid_examples:
        raise SystemExit("Shadow Deep KT を学習するには、最低でも連続した回答ログが3件以上必要です。")

    baseline = baseline_shadow_predictions(train_sequences, valid_sequences)
    num_questions = len(curated["questions"])
    dkt = train_shadow_model("dkt", train_examples, valid_examples, num_questions, epochs, hidden_size, batch_size)
    sakt = train_shadow_model("sakt", train_examples, valid_examples, num_questions, epochs, hidden_size, batch_size)

    candidates = [baseline, dkt, sakt]
    champion = max(
        candidates,
        key=lambda item: (
            item["metrics"]["auc"] if item["metrics"]["auc"] is not None else -item["metrics"]["log_loss"]
        ),
    )
    serializable_models = [
        {key: value for key, value in item.items() if key != "state_dict"}
        for item in [baseline, dkt, sakt]
    ]
    report = {
        "built_at": iso_now(),
        "logs": [str(path) for path in log_paths],
        "data_summary": {
            "events": len(events),
            "attempts": len(attempts),
            "sequences": len(sequences),
            "train_examples": len(train_examples),
            "valid_examples": len(valid_examples),
            "split_strategy": split_strategy,
        },
        "models": serializable_models,
        "champion": champion["model"],
    }
    promotion = build_shadow_promotion(curated, attempts, baseline, champion, len(valid_examples), window)
    SHADOW_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    SHADOW_PROMOTION_PATH.write_text(json.dumps(promotion, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


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
    synthetic_seed = SHADOW_DIR / "synthetic-seed.jsonl"
    if synthetic_seed.exists():
        try:
            run_shadow_training(curated, [synthetic_seed], epochs=8, hidden_size=48, window=12, batch_size=8)
        except SystemExit:
            pass
        else:
            curated = build_curated_payload(payload, count=args.count, days=args.days, daily_hours=args.daily_hours)
            save_curated_payload(curated)
    export_web_data(curated)
    print(f"Exported: {WEB_DATA_PATH}")
    print(f"Questions: {curated['meta']['curated_count']}")


def cmd_shadow_train(args: argparse.Namespace) -> None:
    curated = load_curated_payload()
    log_paths = [Path(path).expanduser() for path in args.logs]
    report = run_shadow_training(
        curated,
        log_paths,
        epochs=args.epochs,
        hidden_size=args.hidden_size,
        window=args.window,
        batch_size=args.batch_size,
    )
    print(f"Shadow report: {SHADOW_REPORT_PATH}")
    print("Data summary:")
    for key, value in report["data_summary"].items():
        print(f"  - {key}: {value}")
    print("Model metrics:")
    for item in report["models"]:
        auc = item["metrics"]["auc"]
        auc_text = f"{auc:.4f}" if auc is not None else "n/a"
        print(
            f"  - {item['model']}: acc {item['metrics']['accuracy']:.4f}, "
            f"logloss {item['metrics']['log_loss']:.4f}, brier {item['metrics']['brier']:.4f}, auc {auc_text}"
        )
    print(f"Champion: {report['champion']}")
    promotion = load_shadow_promotion()
    if promotion:
        print(
            "Promotion:",
            promotion["active_model"],
            "| promoted" if promotion.get("promoted") else "| baseline kept",
            f"| reason {promotion.get('promotion_reason')}",
        )


def load_web_question_lookup() -> Dict[str, Dict[str, object]]:
    source = WEB_DATA_PATH if WEB_DATA_PATH.exists() else CURATED_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    return {question["id"]: question for question in payload.get("questions", [])}


class CSAAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/official-docs":
            self.handle_official_docs(parsed)
            return
        super().do_GET()

    def end_json(self, payload: Dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_official_docs(self, parsed) -> None:
        params = parse_qs(parsed.query)
        question_id = (params.get("questionId") or [None])[0]
        query = (params.get("query") or [None])[0]
        force = (params.get("force") or ["0"])[0] == "1"
        try:
            if question_id:
                lookup = load_web_question_lookup()
                question = lookup.get(question_id)
                if not question:
                    self.end_json({"error": f"unknown questionId: {question_id}"}, status=404)
                    return
                evidence = resolve_official_doc_evidence(question, force_refresh=force)
            elif query:
                evidence = resolve_official_doc_evidence({"doc_basis": {"basis_terms": [query], "primary_topic": query}}, force_refresh=force)
            else:
                self.end_json({"error": "questionId or query is required"}, status=400)
                return
        except Exception as exc:
            self.end_json({"error": str(exc)}, status=502)
            return
        if not evidence:
            self.end_json({"error": "no evidence found"}, status=404)
            return
        self.end_json(evidence)


def cmd_serve(args: argparse.Namespace) -> None:
    host = args.host
    port = args.port
    server = ThreadingHTTPServer((host, port), CSAAppHandler)
    print(f"Serving CSA Spartan on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


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
    concept_tags = extract_adaptive_tags(question)
    release_tags = current_release_tags(concept_tags)
    explanation = build_explanation_ja(question, concept_tags, release_tags)
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
    concept_tags = extract_adaptive_tags(question)
    release_tags = current_release_tags(concept_tags)
    print("Explanation:", build_explanation_ja(question, concept_tags, release_tags))


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

    shadow_train = sub.add_parser("shadow-train", help="Shadow Deep KT (baseline / DKT / SAKT) を学習比較")
    shadow_train.add_argument("logs", nargs="+", help="exported JSONL shadow logs")
    shadow_train.add_argument("--epochs", type=int, default=12)
    shadow_train.add_argument("--hidden-size", type=int, default=64)
    shadow_train.add_argument("--window", type=int, default=24)
    shadow_train.add_argument("--batch-size", type=int, default=12)
    shadow_train.set_defaults(func=cmd_shadow_train)

    serve = sub.add_parser("serve", help="ローカルアプリを公式Docs proxy付きで配信")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8123)
    serve.set_defaults(func=cmd_serve)

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
