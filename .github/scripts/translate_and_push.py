import os
import subprocess
from pathlib import Path
import shutil
import json
import requests

# --- Config ---

SOURCE_INDEX = Path("index.html")

LANGS = {
    "ru": {
        "repo": os.environ["REPO_RU"],
        "label": "Russian",
    },
}

TERMS_TO_KEEP = [
    "lsf", "LSF", "lsFusion", "lsfusion",
    "MITE", "mite", "DevLab", "devlab",
]

GH_TOKEN = os.environ["GH_BOT_TOKEN"]          # GitHub PAT для пушей
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]  # ключ DeepSeek для перевода


def run(cmd, cwd=None, check=True):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check)


def clone_repo(lang: str, repo_full_name: str) -> Path:
    tmp_dir = Path(f"/tmp/devlab-blog-" + lang)
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    url = f"https://x-access-token:{GH_TOKEN}@github.com/{repo_full_name}.git"
    run(["git", "clone", "--depth", "1", url, str(tmp_dir)])
    return tmp_dir


def deepseek_translate_html(html: str, target_lang_label: str) -> str:
    """
    Перевод через DeepSeek API.
    ВАЖНО: проверь в своей документации DeepSeek точный URL и имя модели.
    Здесь стоит типичный openai-совместимый вариант.
    """
    system_prompt = f"""
You are a professional translator.
Translate the user content into {target_lang_label}.

Rules:
- Preserve ALL HTML tags, attributes, structure, and indentation.
- Translate ONLY human-visible text content, not tag names or attributes.
- Do NOT translate code inside <code>, <pre>, or fenced code blocks.
- Do NOT translate brand or product names.
- Keep these terms exactly as-is:
{', '.join(TERMS_TO_KEEP)}

Output ONLY the translated HTML without explanations.
""".strip()

    payload = {
        "model": "deepseek-chat",  # проверь имя модели в кабинете DeepSeek
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": html},
        ],
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    # ⚠️ ПРОВЕРЬ ЭТОТ URL по документации DeepSeek
    url = "https://api.deepseek.com/v1/chat/completions"

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def collect_source_files():
    # Пока тест: только index.html
    if SOURCE_INDEX.is_file():
        return [SOURCE_INDEX]
    return []


def main():
    source_files = collect_source_files()
    if not source_files:
        print("No source files found.")
        return

    # клонируем только ru-репо
    repos = {}
    for lang, cfg in LANGS.items():
        print(f"Cloning {lang} repo: {cfg['repo']}")
        repos[lang] = clone_repo(lang, cfg["repo"])

    changes = {lang: False for lang in LANGS}

    for src in source_files:
        rel = src  # тот же путь в целевом репо
        html = src.read_text(encoding="utf-8")

        for lang, cfg in LANGS.items():
            repo_dir = repos[lang]
            print(f"Translating {rel} → {lang}")

            try:
                translated = deepseek_translate_html(html, cfg["label"])
            except Exception as e:
                print(f"ERROR during translation for {lang}:{rel}: {e}")
                continue

            target_path = repo_dir / rel
            target_path.parent.mkdir(parents=True, exist_ok=True)

            old = None
            if target_path.exists():
                old = target_path.read_text(encoding="utf-8")

            if old == translated:
                print(f"No changes for {lang}:{rel}")
                continue

            target_path.write_text(translated, encoding="utf-8")
            changes[lang] = True
            run(["git", "add", str(rel)], cwd=repo_dir)

    # коммиты и пуши
    for lang, repo_dir in repos.items():
        if not changes[lang]:
            print(f"No updates for {lang}")
            continue

        print(f"Committing & pushing {lang} changes")
        run(["git", "config", "user.name", "devlab-translation-bot"], cwd=repo_dir)
        run(["git", "config", "user.email", "bot@devlab.blog"], cwd=repo_dir)

        try:
            run(["git", "commit", "-m", "Auto-translation sync (DeepSeek, index ru)"], cwd=repo_dir)
            run(["git", "push", "origin", "HEAD:main"], cwd=repo_dir)
        except Exception as e:
            print(f"Push error for {lang}: {e}")


if __name__ == "__main__":
    main()
