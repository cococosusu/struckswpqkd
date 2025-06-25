import hashlib
import json
from pathlib import Path
import ast
import streamlit as st
from collections import defaultdict
from uuid import uuid4

used_keys = set()


def make_safe_key(*args) -> str:
    """중복 방지를 위해 uuid를 활용한 key 생성 (UI용)"""
    base = "memo_" + "_".join(a.replace("/", "_").replace(" ", "_") for a in args)
    key = base
    while key in used_keys:
        key = f"{base}_{uuid4().hex[:8]}"
    used_keys.add(key)
    return key


def make_unique_key(
    file_path: Path, scope_type: str, scope_name: str, parent_name: str = None
) -> str:
    """구조화된 메모 저장을 위한 고유 key 생성"""
    full_path = str(file_path.resolve())
    parts = [full_path, scope_type, scope_name]
    if parent_name:
        parts.append(parent_name)
    raw_key = "::".join(parts)
    hashed = hashlib.md5(raw_key.encode()).hexdigest()
    return f"memo_{raw_key}"


def extract_structure(file_path):
    """파이썬 파일에서 클래스 및 함수 구조 추출"""
    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    classes = defaultdict(list)
    functions = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef):
                    classes[node.name].append(sub.name)
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)

    return {"classes": dict(classes), "functions": functions}


def collect_project_structure(project_path, exclude_folders):
    """전체 프로젝트 구조 수집"""
    structure = defaultdict(dict)
    for py_file in Path(project_path).rglob("*.py"):
        if any(part in exclude_folders for part in py_file.parts):
            continue
        relative_path = py_file.relative_to(project_path)
        folder = str(relative_path.parent)
        structure[folder][py_file.name] = (extract_structure(py_file), py_file)
    return structure


def format_memo_data(memo_data):
    """사람이 읽기 쉬운 메모 형식으로 변환"""
    tree = defaultdict(
        lambda: {
            "__file_memo__": "",
            "__functions__": {},
            "__classes__": defaultdict(dict),
        }
    )

    for key, memo in memo_data.items():
        if not memo.strip():
            continue

        if not key.startswith("memo_"):
            continue

        raw = key[len("memo_") :]
        parts = raw.split("::")
        if len(parts) < 3:
            continue

        path, scope, name = parts[:3]
        parent = parts[3] if len(parts) == 4 else None

        if scope == "file":
            tree[path]["__file_memo__"] = memo
        elif scope == "function":
            tree[path]["__functions__"][name] = memo
        elif scope == "class":
            tree[path]["__classes__"][name]["__memo__"] = memo
        elif scope == "method" and parent:
            tree[path]["__classes__"][parent][name] = memo

    lines = []
    for path, content in sorted(tree.items()):
        rel_path = str(Path(path).relative_to(Path.cwd()))
        lines.append(f"📄 {rel_path}")
        if content["__file_memo__"]:
            lines.append(f"  📌 {content['__file_memo__']}")
        for fn, memo in content["__functions__"].items():
            lines.append(f"  [FUNC] {fn}() : {memo}")
        for cls, cls_content in content["__classes__"].items():
            lines.append(f"  [CLASS] {cls} : {cls_content.get('__memo__', '')}")
            for m_name, m_memo in cls_content.items():
                if m_name != "__memo__":
                    lines.append(f"    └── def {m_name}() : {m_memo}")
        lines.append("")  # 파일 간 구분

    return "\n".join(lines)


def main():
    st.set_page_config(layout="wide")
    st.title("📦 프로젝트 구조 탐색기 + 메모 저장기")

    project_dir = st.text_input("📁 분석할 프로젝트 경로:", value=".")
    exclude_input = st.text_input(
        "🚫 제외할 폴더 (쉼표로 구분):",
        value="__pycache__, .venv, tests, migrations, ai, render, tmp, writer",
    )
    exclude_folders = [e.strip() for e in exclude_input.split(",")]

    if not Path(project_dir).exists():
        st.error("❌ 경로가 존재하지 않아요.")
        return

    with st.spinner("🔍 코드 구조 분석 중..."):
        structure = collect_project_structure(project_dir, exclude_folders)

    st.markdown("---")
    st.subheader("📂 파일별 구조와 메모")

    memo_data = {}

    for folder, files in sorted(structure.items()):
        with st.expander(f"📁 {folder}"):
            for file, (content, py_file_path) in sorted(files.items()):
                file_ui_key = make_safe_key(str(py_file_path), "file", file)
                file_unique_key = make_unique_key(py_file_path, "file", file)
                with st.expander(f"📄 {file}"):
                    file_memo = st.text_area(f"📝 {file} 메모", key=file_ui_key)
                    memo_data[file_unique_key] = file_memo

                    if content["functions"]:
                        st.markdown("#### ⚙️ 전역 함수")
                        for fn in content["functions"]:
                            fn_ui_key = make_safe_key(str(py_file_path), "function", fn)
                            fn_unique_key = make_unique_key(
                                py_file_path, "function", fn
                            )
                            st.markdown(f"- `def {fn}()`")
                            fn_memo = st.text_input(
                                "메모",
                                key=fn_ui_key,
                                label_visibility="collapsed",
                                placeholder="함수 메모...",
                            )
                            memo_data[fn_unique_key] = fn_memo

                    if content["classes"]:
                        st.markdown("#### 🧱 클래스 및 메서드")
                        for cls, methods in content["classes"].items():
                            cls_ui_key = make_safe_key(str(py_file_path), "class", cls)
                            cls_unique_key = make_unique_key(py_file_path, "class", cls)
                            with st.expander(f"🧩 class {cls}"):
                                cls_memo = st.text_input(
                                    "메모",
                                    key=cls_ui_key,
                                    label_visibility="collapsed",
                                    placeholder="클래스 메모...",
                                )
                                memo_data[cls_unique_key] = cls_memo

                                for method in methods:
                                    m_ui_key = make_safe_key(
                                        str(py_file_path), "method", cls, method
                                    )
                                    m_unique_key = make_unique_key(
                                        py_file_path, "method", method, cls
                                    )
                                    st.markdown(f"- `def {method}()`")
                                    m_memo = st.text_input(
                                        "메모",
                                        key=m_ui_key,
                                        label_visibility="collapsed",
                                        placeholder="메서드 메모...",
                                    )
                                    memo_data[m_unique_key] = m_memo

    st.markdown("---")
    st.subheader("📤 메모 내보내기")

    # st.download_button(
    #     label="📥 메모 JSON 다운로드",
    #     data=json.dumps(memo_data, indent=2, ensure_ascii=False),
    #     file_name="project_memo_export.json",
    #     mime="application/json",
    # )

    st.download_button(
        label="📥 메모 TXT 다운로드",
        data=format_memo_data(memo_data),
        file_name="project_memo_export.txt",
        mime="text/plain",
    )


if __name__ == "__main__":
    main()
