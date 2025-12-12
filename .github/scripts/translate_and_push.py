import os
import subprocess
from pathlib import Path
import shutil
import json
import requests

# --- Config ---

SOURCE_INDEX = Path("index.html")
SOURCE_POSTS_DIR = Path("posts")

LANGS = {
    "uk": {
        "repo": os.environ["REPO_UK"],
        "label": "Ukrainian",
    },
    "pl": {
        "repo": os.environ["REPO_PL"],
        "label": "Polish",
    },
    "ru": {
        "repo": os.environ["REPO_RU"],
        "label": "Russian",
    },
}

TERMS_TO_KEEP = [
    "lsf", "LSF", "lsFusion", "lsfusion",
    "MITE", "mite", "DevLab", "devlab",
]

GH_TOKEN = os.environ["GH_BOT_TOKEN"]  # твой PAT для пушей


def run(cmd, cwd=None, check=True):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check)


def clone_repo(lang: str, repo_full_name: str) -> Path:
    tmp_dir = Path(f"/tmp/devlab-blog-{lang}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    url = f"https://x-access-token:{GH_TOKEN}@github.com/{repo_full_name}.git"
    run(["git", "clone", "--depth", "1", url, str(tmp_dir)])
    return tmp_dir


def openai_translate_html(html: str, target_lang_label: str) -> str:
    """
    Переводим через GitHub Models (бесплатно в Actions).
    Используем модель meta-llama-3.1-8b-instruct.
    """
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        # В Actions он всегда есть, но если чего-то пойдёт не так —
        # просто возвращаем оригинал, чтобы не ломать пайплайн.
        print("WARNING: GITHUB_TOKEN is not set, returning original HTML")
        return html

    system_prompt = f"""
You are a professional translator.
Translate the user content into {target_lang_label}.

Rules:
- Preserve ALL HTML tags, attributes, structure, and indentation.
- Translate ONLY visible text content, not tag names or attributes.
- Do NOT translate code inside <code>, <pre>, or fenced code blocks.
- Do NOT translate brand/product names.
- Keep these terms exactly as-is:
{', '.join(TERMS_TO_KEEP)}

Output ONLY the translated HTML without explanations.
""".strip()

    payload = {
        "model": "meta-llama-3.1-8b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": html},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2024-05-01",
    }

    resp = requests.post(
        "https://models.inference.ai.azure.com/v1/chat/completions",
        headers=headers,
        data=json.dumps(payload),
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def collect_source_files():
    files = []
    if SOURCE_INDEX.is_file():
        files.append(SOURCE_INDEX)
    if SOURCE_POSTS_DIR.is_dir():
        for p in SOURCE_POSTS_DIR.rglob("*"):
            if p.is_file():
                files.append(p)
    return files


def main():
    source_files = collect_source_files()
    if not source_files:
        print("No source files found.")
        return

    # клонируем целевые репы
    repos = {}
    for lang, cfg in LANGS.items():
        print(f"Cloning {lang} repo: {cfg['repo']}")
        repos[lang] = clone_repo(lang, cfg["repo"])

    changes = {lang: False for lang in LANGS}

    # пробегаем index.html и все posts/*
    for src in source_files:
        rel = src  # тот же путь в целевом репо
        html = src.read_text(encoding="utf-8")

        for lang, cfg in LANGS.items():
            repo_dir = repos[lang]
            print(f"Translating {rel} → {lang}")

            try:
                translated = openai_translate_html(html, cfg["label"])
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
            run(["git", "commit", "-m", "Auto-translation sync via GitHub Models"], cwd=repo_dir)
            run(["git", "push", "origin", "HEAD:main"], cwd=repo_dir)
        except Exception as e:
            print(f"Push error for {lang}: {e}")


if __name__ == "__main__":
    main()
