import json
from html import escape
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.bot.utils.i18n import t
from app.config import settings


MINIAPP_SUPPORTED_LEVELS = {
    "hsk1": (1, 15),
    "hsk2": (1, 15),
    "hsk3": (1, 20),
    "hsk4": (1, 20),
}


def normalize_miniapp_lang(lang: str | None) -> str:
    normalized = (lang or "").strip().lower()
    if normalized in {"tg", "tg-cyrl"}:
        return "tj"
    if normalized in {"uz", "ru", "tj"}:
        return normalized
    return "uz"


def course_miniapp_lesson_id(lesson) -> int:
    return int(getattr(lesson, "lesson_order", None) or getattr(lesson, "id", 0) or 0)


def is_course_miniapp_supported(lesson) -> bool:
    if lesson is None:
        return False

    level = (getattr(lesson, "level", "") or "").strip().lower()
    lesson_id = course_miniapp_lesson_id(lesson)
    lesson_range = MINIAPP_SUPPORTED_LEVELS.get(level)
    if not lesson_range:
        return False

    min_lesson, max_lesson = lesson_range
    return min_lesson <= lesson_id <= max_lesson


def _miniapp_base_url_for_file(target_file: str) -> str:
    base_url = (
        (settings.MINI_APP_BASE_URL or "").strip()
        or "https://telegram-chinese-bot-production.up.railway.app/study.html"
    )

    parts = urlsplit(base_url)
    if parts.path.endswith(".html"):
        path = parts.path.rsplit("/", 1)[0] + f"/{target_file}"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    return base_url.rstrip("/") + f"/{target_file}"


def _miniapp_base_url_for_level(level: str) -> str:
    normalized_level = (level or "").strip().lower()
    target_file = {
        "hsk1": "hsk1.html",
        "hsk2": "hsk2.html",
        "hsk4": "hsk4.html",
    }.get(normalized_level, "hsk3.html")
    return _miniapp_base_url_for_file(target_file)


def course_miniapp_url(lesson, mode: str, lang: str | None = None, block_no: int | None = None) -> str:
    level = (getattr(lesson, "level", "") or "").strip().lower()
    base_url = _miniapp_base_url_for_level(level)
    separator = "&" if "?" in base_url else "?"
    params = {
        "lesson": course_miniapp_lesson_id(lesson),
        "mode": mode,
        "lang": normalize_miniapp_lang(lang),
    }
    if block_no:
        params["block"] = int(block_no)
    query = urlencode(params)
    return f"{base_url}{separator}{query}"


def course_stroke_order_url(
    lesson,
    lang: str | None = None,
    block_no: int | None = None,
    vocab_page: int | None = None,
) -> str:
    base_url = _miniapp_base_url_for_file("stroke-order.html")
    separator = "&" if "?" in base_url else "?"
    params = {
        "lesson": course_miniapp_lesson_id(lesson),
        "level": (getattr(lesson, "level", "") or "hsk1").strip().lower(),
        "lang": normalize_miniapp_lang(lang),
    }
    if block_no:
        params["block"] = int(block_no)
    if vocab_page in {1, 2}:
        params["vocab_page"] = int(vocab_page)
    return f"{base_url}{separator}{urlencode(params)}"


def format_miniapp_quiz_intro(lang: str, lesson, block_no: int | None = None) -> str:
    text = t("course_miniapp_quiz_intro", lang, lesson_id=course_miniapp_lesson_id(lesson))
    if not block_no:
        return text
    labels = {
        "uz": f"\n\nQism {block_no} bo'yicha qisqa test.",
        "ru": f"\n\nКороткий тест по части {block_no}.",
        "tj": f"\n\nТести кӯтоҳ аз рӯи қисми {block_no}.",
    }
    return text + labels.get(lang, labels["ru"])


def format_miniapp_homework_intro(lang: str, lesson) -> str:
    return t("course_miniapp_homework_intro", lang, lesson_id=course_miniapp_lesson_id(lesson))


def normalize_result_items(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return [line.strip() for line in raw.splitlines() if line.strip()]
        return normalize_result_items(parsed)

    if not isinstance(value, list):
        return [str(value)]

    items = []
    for item in value:
        if isinstance(item, dict):
            question = item.get("question") or item.get("title") or item.get("text") or ""
            answer = item.get("correct_answer") or item.get("answer") or ""
            explanation = item.get("explanation") or item.get("feedback") or ""
            parts = [str(part).strip() for part in (question, answer, explanation) if str(part).strip()]
            if parts:
                items.append(" — ".join(parts[:2]) if len(parts) > 1 else parts[0])
            continue

        text = str(item).strip()
        if text:
            items.append(text)

    return items


def _append_items(lines: list[str], title: str, items: list[str], limit: int = 10) -> None:
    if not items:
        return

    lines.append("")
    lines.append(title)
    for item in items[:limit]:
        lines.append(f"— {escape(str(item))}")


def format_miniapp_quiz_result(lang: str, result: dict) -> str:
    lesson_id = int(result.get("lesson_id") or 0)
    block_no = int(result.get("block_no") or 0)
    score = int(result.get("score") or 0)
    total = int(result.get("total") or 0)
    percent = int(result.get("percent") or 0)
    wrong_items = normalize_result_items(result.get("wrong_items"))

    lines = [
        t("course_miniapp_quiz_done", lang),
        "",
        t("course_miniapp_lesson_line", lang, lesson_id=lesson_id),
        t("course_miniapp_score_line", lang, score=score, total=total, percent=percent),
    ]
    if block_no:
        labels = {
            "uz": f"📍 Qism: {block_no}",
            "ru": f"📍 Часть: {block_no}",
            "tj": f"📍 Қисм: {block_no}",
        }
        lines.insert(3, labels.get(lang, labels["ru"]))
    _append_items(lines, t("course_miniapp_wrong_items", lang), wrong_items)
    if block_no:
        next_text = {
            "uz": "Keyingi qismga o'tamiz.",
            "ru": "Переходим к следующей части.",
            "tj": "Ба қисми навбатӣ мегузарем.",
        }
        lines.extend(["", next_text.get(lang, next_text["ru"])])
    else:
        lines.extend(["", t("course_miniapp_understood_question", lang)])
    return "\n".join(lines)


def format_miniapp_homework_result(lang: str, result: dict) -> str:
    lesson_id = int(result.get("lesson_id") or 0)
    homework_score = result.get("homework_score")
    feedback_items = normalize_result_items(result.get("feedback"))

    lines = [
        t("course_miniapp_homework_done", lang),
        "",
        t("course_miniapp_lesson_line", lang, lesson_id=lesson_id),
    ]

    if homework_score is not None:
        try:
            score_text = str(int(homework_score))
        except (TypeError, ValueError):
            score_text = escape(str(homework_score))
        lines.extend(["", t("course_miniapp_homework_score_line", lang, score=score_text)])

    _append_items(lines, t("course_miniapp_feedback_items", lang), feedback_items)
    return "\n".join(lines)
