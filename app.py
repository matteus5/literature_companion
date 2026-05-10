import re
import io
import jieba
import yake
import langdetect
import nltk
import streamlit as st
from deep_translator import GoogleTranslator
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
import pdfplumber
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm

# 【修复1】自动下载NLTK必需数据，解决sumy崩溃
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

# ===================== 页面配置（无广告、样式固定） =====================
st.set_page_config(
    page_title="文献伴侣智能体",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 【修复2】简化CSS，避免前端DOM冲突
hide_style = """
<style>
#MainMenu, footer, header, .stDeployButton, div[data-testid="stToolbar"] {visibility: hidden; height: 0; width: 0;}
* {color: #1e293b !important;}
.stApp {background-color: #f8fafc;}
</style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ===================== 稳定的会话状态初始化 =====================
default_states = {
    "step": "menu",
    "paper_text": "",
    "meta": {"title":"","author":"","year":"","journal":"","volume":"","pages":""},
    "summary_data": {},
    "pdf_generated": False,
    "pdf_bytes": None
}
for key, val in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ===================== 工具函数：PDF文本提取 =====================
def extract_pdf_text(pdf_file):
    try:
        with pdfplumber.open(pdf_file) as pdf:
            return "\n".join([page.extract_text() or "" for page in pdf.pages])
    except:
        try:
            reader = PdfReader(pdf_file)
            return "\n".join([page.extract_text() or "" for page in reader.pages])
        except:
            return ""

# ===================== 工具函数：元数据提取 =====================
def extract_metadata(text):
    meta = {k:"" for k in ["title","author","year","journal","volume","pages"]}
    year_match = re.search(r'20\d{2}|19\d{2}', text)
    if year_match: meta["year"] = year_match.group()
    page_match = re.search(r'pp\.\s*\d+-\d+|\d+-\d+页', text)
    if page_match: meta["pages"] = page_match.group()
    vol_match = re.search(r'Vol\.\s*\d+|卷\s*\d+', text)
    if vol_match: meta["volume"] = vol_match.group()
    return meta

# ===================== 工具函数：语言检测 =====================
def detect_lang(text):
    try:
        return langdetect.detect(text[:500])
    except:
        return "zh"

# ===================== 工具函数：摘要生成 =====================
def generate_summary(text, lang):
    try:
        if lang == "en":
            parser = PlaintextParser.from_string(text, Tokenizer("english"))
            sents = [str(s) for s in LsaSummarizer()(parser.document, 3)]
        else:
            sentences = re.split(r'[。！？；]', text)
            sents = [s.strip() for s in sentences if len(s.strip())>10][:3]
        
        core = sents[0] if sents else "无内容"
        detail = "。".join(sents[1:]) if len(sents)>1 else core
        return core, detail
    except:
        return "摘要生成失败", "摘要生成失败"

# ===================== 工具函数：关键词提取 =====================
def get_keywords(text):
    try:
        kw = yake.KeywordExtractor(top=3, dedupLim=0.8).extract_keywords(text)
        return [k[0] for k in kw[:3]]
    except:
        return ["无关键词"]

# ===================== 工具函数：翻译（稳定版） =====================
def translate(text, src, dest):
    try:
        if not text: return ""
        return GoogleTranslator(source=src, target=dest).translate(text)
    except:
        return "翻译失败（检查网络）"

# ===================== 工具函数：引用格式生成 =====================
def gen_citation(meta):
    a = meta["author"] or "Anonymous"
    y = meta["year"] or "n.d."
    t = meta["title"] or "Untitled"
    j = meta["journal"] or "Unknown Journal"
    v = meta["volume"] or ""
    p = meta["pages"] or ""
    apa = f"{a}. ({y}). {t}. {j}, {v}, {p}."
    mla = f"{a}. \"{t}.\" {j}, vol. {v}, {y}, pp. {p}."
    return apa, mla

# ===================== 【修复3】内存生成PDF，无路径报错 =====================
def create_pdf_bytes(orig, trans):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    style = ParagraphStyle(fontSize=9, textColor="#1e293b")
    
    orig_lines = orig.split("\n")[:100]
    trans_lines = trans.split("\n")[:100]
    max_len = max(len(orig_lines), len(trans_lines))
    
    for i in range(max_len):
        o = orig_lines[i] if i<len(orig_lines) else ""
        t = trans_lines[i] if i<len(trans_lines) else ""
        story.append(Paragraph(f"原文：{o}<br/>译文：{t}", style))
        story.append(Spacer(1, 2*mm))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ===================== 主交互逻辑（无rerun，解决DOM报错） =====================
st.title("📚 文献伴侣智能体 | 华师大学生专用")
st.divider()

# 菜单页面
if st.session_state.step == "menu":
    st.subheader("选择输入方式")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("1️⃣ 粘贴论文文本", use_container_width=True):
            st.session_state.step = "input_text"
    with col2:
        if st.button("2️⃣ 上传PDF文件", use_container_width=True):
            st.session_state.step = "input_pdf"

# 文本输入
elif st.session_state.step == "input_text":
    st.subheader("粘贴论文全文")
    text = st.text_area("论文内容", height=300)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("开始分析", use_container_width=True):
            if text.strip():
                st.session_state.paper_text = text
                st.session_state.step = "analyze"
            else:
                st.warning("请输入内容")
    with col2:
        if st.button("返回菜单", use_container_width=True):
            st.session_state.step = "menu"

# PDF上传
elif st.session_state.step == "input_pdf":
    st.subheader("上传文字型PDF")
    file = st.file_uploader("选择PDF", type="pdf")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("提取并分析", use_container_width=True) and file:
            with st.spinner("解析PDF中..."):
                text = extract_pdf_text(file)
            if text:
                st.session_state.paper_text = text
                st.session_state.step = "analyze"
            else:
                st.error("PDF解析失败")
    with col2:
        if st.button("返回菜单", use_container_width=True):
            st.session_state.step = "menu"

# 分析结果页（核心修复：无强制刷新）
elif st.session_state.step == "analyze":
    text = st.session_state.paper_text
    if not st.session_state.summary_data:
        with st.spinner("文献分析中..."):
            # 自动处理
            lang = detect_lang(text)
            src = "zh-CN" if lang=="zh" else "en"
            dest = "en" if lang=="zh" else "zh-CN"
            st.session_state.meta.update(extract_metadata(text))
            core, detail = generate_summary(text, lang)
            kw = get_keywords(text)
            
            # 双语翻译
            st.session_state.summary_data = {
                "lang": lang, "src": src, "dest": dest,
                "core": core, "core_t": translate(core, src, dest),
                "detail": detail, "detail_t": translate(detail, src, dest),
                "kw": kw, "kw_t": [translate(k, src, dest) for k in kw]
            }

    # 元数据补全
    st.subheader("📋 补充文献信息")
    meta = st.session_state.meta
    c1, c2, c3 = st.columns(3)
    with c1:
        meta["title"] = st.text_input("论文标题", meta["title"])
        meta["author"] = st.text_input("作者(多作者用;分隔)", meta["author"])
    with c2:
        meta["year"] = st.text_input("发表年份", meta["year"])
        meta["journal"] = st.text_input("期刊/会议", meta["journal"])
    with c3:
        meta["volume"] = st.text_input("卷号", meta["volume"])
        meta["pages"] = st.text_input("页码", meta["pages"])

    # 双语结果展示
    st.divider()
    st.subheader("📝 双语摘要 & 关键词")
    sd = st.session_state.summary_data
    if sd["lang"] == "zh":
        st.markdown(f"""
        **核心观点（中文）**：{sd['core']}  
        **核心观点（英文）**：{sd['core_t']}  

        **详细摘要（中文）**：{sd['detail']}  
        **详细摘要（英文）**：{sd['detail_t']}  

        **关键论点**：{" | ".join(sd['kw'])}  
        **英文关键词**：{" | ".join(sd['kw_t'])}
        """)
    else:
        st.markdown(f"""
        **Core View**：{sd['core']}  
        **核心观点**：{sd['core_t']}  

        **Abstract**：{sd['detail']}  
        **详细摘要**：{sd['detail_t']}  

        **Key Words**：{" | ".join(sd['kw'])}  
        **中文关键词**：{" | ".join(sd['kw_t'])}
        """)

    # 引用格式
    st.divider()
    st.subheader("📌 标准引用格式")
    apa, mla = gen_citation(meta)
    st.text_area("APA格式", apa, height=80)
    st.text_area("MLA格式", mla, height=80)

    # 对照PDF生成（内存模式，无报错）
    st.divider()
    st.subheader("📄 生成对照PDF")
    if st.button("生成原文+译文对照PDF"):
        with st.spinner("翻译并生成PDF..."):
            full_t = translate(text, sd["src"], sd["dest"])
            st.session_state.pdf_bytes = create_pdf_bytes(text, full_t)
        st.success("PDF生成完成！")

    if st.session_state.pdf_bytes:
        st.download_button("💾 下载PDF", st.session_state.pdf_bytes, "文献对照.pdf", use_container_width=True)

    # 重置对话（安全模式，不破坏DOM）
    st.divider()
    if st.button("🔄 开始新对话", use_container_width=True):
        for key in default_states:
            st.session_state[key] = default_states[key]
