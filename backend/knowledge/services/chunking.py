import re

from langchain_text_splitters import RecursiveCharacterTextSplitter


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)    # 一个或多个空格/Tab
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Split recursively at paragraph/sentence boundaries, then characters."""
    if overlap < 0 or chunk_size <= overlap:
        raise ValueError("chunk_size 必须大于 overlap，且 overlap 不能为负数。")
    text = normalize_text(text)
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", "!", "?", "；", ";", "，", ",", " ", ""],
        keep_separator="end",
        length_function=len,
        is_separator_regex=False,
    )
    return splitter.split_text(text)
