import re
import jieba
import yake
import langdetect
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
import streamlit as st

# ===================== 全局样式配置 匹配你的界面要求 =====================
st.set_page_config(
    page_title="文献伴侣智能体",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 隐藏Streamlit默认菜单、工具栏、脚注、部署按钮
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stDeployButton {display:none;}
div[data-testid="stToolbar"] {display:none;}
/* 全局文字深灰色 #1e293b */
* {
    color: #1e293b !important;
}
/* 浅色背景 */
.stApp {
    background-color: #f8fafc;
}
/* 输入框清除残留、防卡顿 */
.stTextInput>div>div>input {
    background-color: #ffffff;
}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ===================== 初始化会话状态 =====================
if "step" not in st.session_state:
    st.session_state.step = "menu"
if "paper_text" not in st.session_state:
    st.session_state.paper_text = ""
if "meta" not in st.session_state:
    st.session_state.meta = {
        "title": "", "author": "", "year": "",
        "journal": "", "volume": "", "pages": ""
    }
if "summary_data" not in st.session_state:
    st.session_state.summary_data = {}

# ===================== 工具函数1：PDF文字提取 =====================
def extract_pdf_text(pdf_file):
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = "\n".join([page.extract_text() or "" for page in pdf.pages])
        if text.strip():
            return text
    except:
        pass
    # 后备 PyPDF2
    reader = PdfReader(pdf_file)
    text = "\n".join([page.extract_text() or "" for page in reader.pages])
    return text

# ===================== 工具函数2：自动元数据正则提取 =====================
def extract_metadata(text):
    meta = {"title":"","author":"","year":"","journal":"","volume":"","pages":""}
    # 年份匹配 4位数字
    year_match = re.search(r'20\d{2}|19\d{2}', text)
    if year_match:
        meta["year"] = year_match.group()
    # 页码匹配
    page_match = re.search(r'pp\.\s*\d+-\d+|\d+-\d+页', text)
    if page_match:
        meta["pages"] = page_match.group()
    # 卷号匹配
    vol_match = re.search(r'Vol\.\s*\d+|卷\s*\d+', text)
    if vol_match:
        meta["volume"] = vol_match.group()
    return meta

# ===================== 工具函数3：语言检测 =====================
def detect_language(text):
    try:
        return langdetect.detect(text[:500])
    except:
        return "zh"

# ===================== 工具函数4：生成摘要 中英文分流 =====================
def generate_summary(text, lang):
    # 一句话核心观点 + 2-3句详细摘要
    if lang == "en":
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        summary_sents = summarizer(parser.document, 3)
        sents = [str(s) for s in summary_sents]
    else:
        # 中文结巴分词分句
        sentences = re.split(r'[。！？；]', text)
        sentences = [s.strip() for s in sentences if len(s.strip())>10]
        sents = sentences[:3]
    
    core_view = sents[0] if sents else "无核心观点"
    detail_abs = "。".join(sents[1:]) if len(sents)>1 else "无详细摘要"
    return core_view, detail_abs

# ===================== 工具函数5：Yake关键词提取 =====================
def get_keywords(text, lang):
    kw_extractor = yake.KeywordExtractor(top=3, dedupLim=0.8)
    keywords = kw_extractor.extract_keywords(text)
    return [kw[0] for kw in keywords[:3]]

# ===================== 工具函数6：双语翻译 =====================
def translate_text(text, src, dest):
    try:
        return GoogleTranslator(source=src, target=dest).translate(text)
    except:
        return "翻译失败，请检查网络"

# ===================== 工具函数7：生成APA/MLA引用 =====================
def gen_citation(meta):
    author = meta["author"] or "佚名"
    year = meta["year"] or "未知年份"
    title = meta["title"] or "未知标题"
    journal = meta["journal"] or "未知期刊"
    vol = meta["volume"] or ""
    pages = meta["pages"] or ""

    apa = f"{author}. ({year}). {title}. {journal}, {vol}, {pages}."
    mla = f"{author}. \"{title}.\" {journal}, vol.{vol}, {year}, pp.{pages}."
    return apa, mla

# ===================== 工具函数8：生成左右对照PDF =====================
def create_compare_pdf(orig_text, trans_text, save_path):
    doc = SimpleDocTemplate(save_path, pagesize=A4)
    story = []
    style_left = ParagraphStyle(name="Left", fontSize=9, textColor="#1e293b")
    style_right = ParagraphStyle(name="Right", fontSize=9, textColor="#1e293b")

    # 分行对照
    orig_lines = orig_text.split("\n")[:80]
    trans_lines = trans_text.split("\n")[:80]
    max_len = max(len(orig_lines), len(trans_lines))

    for i in range(max_len):
        o_line = orig_lines[i] if i<len(orig_lines) else ""
        t_line = trans_lines[i] if i<len(trans_lines) else ""
        line_text = f"原文：{o_line}<br/>译文：{t_line}"
        p = Paragraph(line_text, style_left)
        story.append(p)
        story.append(Spacer(1, 2*mm))
    doc.build(story)
    return save_path

# ===================== 主交互逻辑 =====================
st.title("📚 文献伴侣智能体 | 华师大学生专用")
st.divider()

# 步骤1：菜单选择
if st.session_state.step == "menu":
    st.subheader("请选择输入方式")
    opt1 = st.button("1️⃣ 粘贴论文文本")
    opt2 = st.button("2️⃣ 上传PDF文件")
    if opt1:
        st.session_state.step = "input_text"
        st.rerun()
    if opt2:
        st.session_state.step = "input_pdf"
        st.rerun()

# 步骤2：粘贴文本输入
elif st.session_state.step == "input_text":
    st.subheader("请粘贴论文全文")
    text = st.text_area("论文文本区域", height=300)
    if st.button("开始分析文献"):
        if text.strip():
            st.session_state.paper_text = text
            st.session_state.step = "analyze"
            st.rerun()
        else:
            st.warning("请输入论文内容")
    if st.button("返回菜单"):
        st.session_state.step = "menu"
        st.rerun()

# 步骤3：上传PDF
elif st.session_state.step == "input_pdf":
    st.subheader("上传文字型PDF文件（非扫描图片）")
    pdf_file = st.file_uploader("选择PDF", type="pdf")
    if pdf_file and st.button("提取并分析"):
        with st.spinner("正在解析PDF..."):
            text = extract_pdf_text(pdf_file)
        if text.strip():
            st.session_state.paper_text = text
            st.session_state.step = "analyze"
            st.rerun()
        else:
            st.error("PDF解析失败，请确认是文字型PDF")
    if st.button("返回菜单"):
        st.session_state.step = "menu"
        st.rerun()

# 步骤4：自动分析 + 元数据补全 + 双语结果
elif st.session_state.step == "analyze":
    with st.spinner("文献智能分析中，请稍候..."):
        text = st.session_state.paper_text
        # 1.语言检测
        lang = detect_language(text)
        src_lang = "zh-CN" if lang=="zh" else "en"
        dest_lang = "en" if lang=="zh" else "zh-CN"
        # 2.自动提取元数据
        auto_meta = extract_metadata(text)
        st.session_state.meta.update(auto_meta)
        # 3.生成摘要、关键词
        core_view, detail_abs = generate_summary(text, lang)
        keywords = get_keywords(text, lang)
        # 4.双语翻译
        core_view_trans = translate_text(core_view, src_lang, dest_lang)
        detail_abs_trans = translate_text(detail_abs, src_lang, dest_lang)
        keywords_trans = [translate_text(k, src_lang, dest_lang) for k in keywords]
        # 缓存结果
        st.session_state.summary_data = {
            "lang":lang, "core":core_view, "core_trans":core_view_trans,
            "detail":detail_abs, "detail_trans":detail_abs_trans,
            "kw":keywords, "kw_trans":keywords_trans
        }

    # 缺失元数据手动补充
    st.subheader("📋 补充文献元数据（未自动识别的请手动填写）")
    meta = st.session_state.meta
    col1,col2,col3 = st.columns(3)
    with col1:
        meta["title"] = st.text_input("论文标题", value=meta["title"])
        meta["author"] = st.text_input("作者（多作者用分号分隔）", value=meta["author"])
    with col2:
        meta["year"] = st.text_input("发表年份", value=meta["year"])
        meta["journal"] = st.text_input("期刊/会议名称", value=meta["journal"])
    with col3:
        meta["volume"] = st.text_input("卷号", value=meta["volume"])
        meta["pages"] = st.text_input("页码", value=meta["pages"])
    st.session_state.meta = meta

    # 展示双语摘要&关键词
    st.divider()
    st.subheader("📝 双语摘要 & 关键词")
    sd = st.session_state.summary_data
    if sd["lang"] == "zh":
        st.markdown(f"""
        **核心观点（中文）**：{sd['core']}  
        **核心观点（英文）**：{sd['core_trans']}  

        **详细摘要（中文）**：{sd['detail']}  
        **详细摘要（英文）**：{sd['detail_trans']}  

        **关键论点（中文）**：{" | ".join(sd['kw'])}  
        **关键论点（英文）**：{" | ".join(sd['kw_trans'])}
        """)
    else:
        st.markdown(f"""
        **Core View (English)**：{sd['core']}  
        **核心观点（中文）**：{sd['core_trans']}  

        **Abstract (English)**：{sd['detail']}  
        **详细摘要（中文）**：{sd['detail_trans']}  

        **Key Words (English)**：{" | ".join(sd['kw'])}  
        **关键论点（中文）**：{" | ".join(sd['kw_trans'])}
        """)

    # 生成引用格式
    st.divider()
    st.subheader("📌 标准参考文献格式")
    apa, mla = gen_citation(meta)
    st.text_area("APA 格式", value=apa, height=80)
    st.text_area("MLA 格式", value=mla, height=80)

    # 生成左右对照PDF
    st.divider()
    st.subheader("📄 生成左右对照PDF（原文+译文）")
    if st.button("生成对照PDF"):
        with st.spinner("正在生成PDF..."):
            full_trans = translate_text(st.session_state.paper_text, src_lang, dest_lang)
            pdf_path = "/tmp/文献对照.pdf"
            create_compare_pdf(st.session_state.paper_text, full_trans, pdf_path)
        with open(pdf_path, "rb") as f:
            st.download_button("一键下载对照PDF", f, file_name="文献左右对照.pdf")

    # 重置新对话
    if st.button("🔄 新对话 重置"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
