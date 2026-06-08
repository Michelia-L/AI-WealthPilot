"""
AI WealthPilot - Premium Style Injection Module
AI WealthPilot - 高级样式注入模块

This module defines the global CSS styling and typography overrides 
to achieve a premium "Obsidian & Gold Glassmorphism" financial terminal aesthetic.
"""

import streamlit as st

def inject_premium_styles() -> None:
    """
    Inject custom CSS globally to override Streamlit's default styling.
    """
    st.markdown(
        """
        <style>
        /* ============================================================
           1. Fonts & Global Settings
           ============================================================ */
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

        /* Set global body typography */
        html, body, [class*="css"], .stApp {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

        /* Modern geometric headers - Solid high-contrast text to preserve color emoji rendering */
        h1 {
            font-family: 'Outfit', sans-serif !important;
            letter-spacing: -0.02em !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            text-shadow: 0 0 20px rgba(255, 255, 255, 0.05);
            padding-bottom: 0.15em;
        }

        h2, h3 {
            font-family: 'Outfit', sans-serif !important;
            letter-spacing: -0.015em !important;
            color: #f8fafc !important;
            font-weight: 600 !important;
            padding-bottom: 0.1em;
        }

        .brand-title {
            font-family: 'Outfit', sans-serif !important;
            color: #d4af37 !important;
            font-weight: 700 !important;
            text-shadow: 0 0 10px rgba(212, 175, 55, 0.1);
        }

        /* Adjust normal markdown header colors */
        h4, h5, h6 {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-weight: 600 !important;
            color: #f8fafc !important;
            letter-spacing: -0.01em !important;
        }

        /* Main app background with OLED black & organic radial mesh gradient */
        [data-testid="stAppViewContainer"] {
            background-color: #050505 !important;
            background-image: 
                radial-gradient(circle at 50% -20%, rgba(212, 175, 55, 0.08) 0%, rgba(212, 175, 55, 0) 50%),
                radial-gradient(circle at 10% 20%, rgba(26, 16, 60, 0.25) 0%, rgba(26, 16, 60, 0) 40%),
                radial-gradient(circle at 90% 80%, rgba(16, 185, 129, 0.04) 0%, rgba(16, 185, 129, 0) 50%) !important;
            background-attachment: fixed !important;
        }

        [data-testid="stHeader"] {
            background-color: transparent !important;
        }

        /* ============================================================
           2. Sidebar Navigation (Vantablack Glassmorphism & Spring Tabs)
           ============================================================ */
        [data-testid="stSidebar"] {
            background-color: rgba(5, 5, 5, 0.85) !important;
            backdrop-filter: blur(25px) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
            box-shadow: 10px 0 40px rgba(0, 0, 0, 0.6) !important;
        }

        /* Sidebar vertical block spacing */
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            padding: 2.5rem 1.25rem !important;
        }

        /* Custom Sidebar Title Styling (Cinzel for Heritage/Brand identity) */
        .sidebar-brand {
            font-family: 'Cinzel', serif !important;
            font-size: 1.45rem !important;
            font-weight: 700 !important;
            background: linear-gradient(135deg, #f3e7c4 0%, #d4af37 50%, #aa7c11 100%) !important;
            -webkit-background-clip: text !important;
            -webkit-text-fill-color: transparent !important;
            text-align: center;
            margin-bottom: 0.25rem;
            letter-spacing: 0.05em;
        }
        
        .sidebar-subtitle {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 0.78rem !important;
            font-weight: 500;
            color: #94a3b8 !important;
            text-align: center;
            margin-bottom: 1.5rem;
            opacity: 0.8;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        /* Hide Streamlit default circular radio inputs and style label as premium tabs */
        [data-testid="stSidebar"] [data-testid="stRadio"] label {
            display: flex !important;
            align-items: center !important;
            padding: 12px 18px !important;
            margin-bottom: 12px !important;
            border-radius: 12px !important;
            background: rgba(255, 255, 255, 0.01) !important;
            border: 1px solid rgba(255, 255, 255, 0.04) !important;
            cursor: pointer !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
            color: #94a3b8 !important;
            font-size: 0.95rem !important;
            font-weight: 500 !important;
        }
        
        [data-testid="stSidebar"] [data-testid="stRadio"] label p {
            color: #94a3b8 !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }

        /* Hide the default radio circle */
        [data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child {
            display: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label input {
            position: absolute;
            opacity: 0;
            cursor: pointer;
        }

        /* Sidebar tabs hover effect - spring translation and scaling */
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
            background: rgba(255, 255, 255, 0.03) !important;
            border-color: rgba(212, 175, 55, 0.25) !important;
            color: #ffffff !important;
            transform: translateX(6px) scale(1.02) !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover p {
            color: #ffffff !important;
        }

        /* Sidebar tabs active selected state */
        [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
            background: rgba(212, 175, 55, 0.06) !important;
            border-color: rgba(212, 175, 55, 0.6) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 24px rgba(212, 175, 55, 0.08), inset 0 1px 1px rgba(255, 255, 255, 0.1) !important;
            font-weight: 600 !important;
            transform: translateX(2px) !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
            color: #ffffff !important;
            font-weight: 600 !important;
        }

        /* ============================================================
           3. Double-Bezel Card Enclosure (Hardware Look)
           ============================================================ */
        .bezel-card {
            background: rgba(255, 255, 255, 0.02) !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 24px !important;
            padding: 8px !important;
            margin-bottom: 16px !important;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4) !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }
        
        .bezel-card:hover {
            transform: translateY(-4px) scale(1.01) !important;
            border-color: rgba(212, 175, 55, 0.35) !important;
            background: rgba(212, 175, 55, 0.02) !important;
            box-shadow: 0 20px 48px rgba(212, 175, 55, 0.08), 0 12px 40px rgba(0, 0, 0, 0.4) !important;
        }
        
        .inner-core {
            background: #09090b !important;
            border: 1px solid rgba(255, 255, 255, 0.03) !important;
            border-radius: 16px !important; /* calc(24px - 8px) = 16px concentric radius */
            padding: 20px !important;
            box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.08) !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }
        
        .bezel-card:hover .inner-core {
            border-color: rgba(212, 175, 55, 0.25) !important;
            box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.12) !important;
        }

        /* Metric Cards - Native overrides styled as inner-core cards */
        [data-testid="stMetric"] {
            background: #09090b !important;
            border: 1px solid rgba(255, 255, 255, 0.04) !important;
            border-radius: 16px !important;
            padding: 18px 22px !important;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.08) !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }

        [data-testid="stMetric"]:hover {
            border-color: rgba(212, 175, 55, 0.3) !important;
            box-shadow: 0 15px 40px rgba(212, 175, 55, 0.08), inset 0 1px 1px rgba(255, 255, 255, 0.12), 0 10px 30px rgba(0, 0, 0, 0.3) !important;
            transform: translateY(-3px) !important;
        }

        [data-testid="stMetricLabel"] {
            color: #94a3b8 !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.08em !important;
            text-transform: uppercase !important;
        }

        [data-testid="stMetricValue"] {
            color: #ffffff !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 1.85rem !important;
            font-weight: 700 !important;
            margin-top: 6px !important;
        }

        /* ============================================================
           4. Form Buttons (Luxury Gradients & Spring Scale)
           ============================================================ */
        /* Primary buttons - Gold Pill with shine */
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #f3e7c4 0%, #d4af37 50%, #aa7c11 100%) !important;
            color: #050505 !important;
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            border: none !important;
            border-radius: 9999px !important;
            padding: 10px 28px !important;
            box-shadow: 0 6px 20px rgba(212, 175, 55, 0.15) !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
            letter-spacing: 0.02em;
        }

        div.stButton > button[kind="primary"]:hover {
            box-shadow: 0 12px 30px rgba(212, 175, 55, 0.3) !important;
            transform: translateY(-2px) scale(1.02) !important;
            filter: brightness(1.05) !important;
        }
        
        div.stButton > button[kind="primary"]:active {
            transform: translateY(0px) scale(0.97) !important;
        }

        /* Secondary/Normal buttons - Glass border pill */
        div.stButton > button[kind="secondary"] {
            background: rgba(255, 255, 255, 0.02) !important;
            color: #d4af37 !important;
            font-family: 'Outfit', sans-serif !important;
            font-weight: 500 !important;
            border: 1px solid rgba(212, 175, 55, 0.3) !important;
            border-radius: 9999px !important;
            padding: 10px 28px !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }

        div.stButton > button[kind="secondary"]:hover {
            background: rgba(212, 175, 55, 0.06) !important;
            border-color: #d4af37 !important;
            box-shadow: 0 8px 24px rgba(212, 175, 55, 0.12) !important;
            transform: translateY(-2px) scale(1.02) !important;
            color: #ffffff !important;
        }

        div.stButton > button[kind="secondary"]:active {
            transform: translateY(0px) scale(0.97) !important;
        }

        /* ============================================================
           5. Form Inputs (Sleek Dark Theme UI)
           ============================================================ */
        /* Style selectbox container - explicit height and padding to ensure vertical centering and no text clipping */
        [data-testid="stSelectbox"] > div[data-baseweb="select"] > div {
            background-color: rgba(255, 255, 255, 0.02) !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 12px !important;
            height: 42px !important;
            padding: 0 12px !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }

        /* Style text/number/textarea inputs */
        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {
            background-color: rgba(255, 255, 255, 0.02) !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            color: #f8fafc !important;
            border-radius: 12px !important;
            padding: 8px 16px !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            transition: all 600ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }

        [data-testid="stSelectbox"] > div[data-baseweb="select"] > div:focus-within,
        [data-testid="stNumberInput"] input:focus,
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {
            border-color: rgba(212, 175, 55, 0.5) !important;
            box-shadow: 0 0 0 2px rgba(212, 175, 55, 0.15) !important;
            background-color: rgba(255, 255, 255, 0.04) !important;
        }

        /* Expander panels */
        [data-testid="stExpander"] {
            background-color: rgba(9, 9, 11, 0.6) !important;
            backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 16px !important;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2) !important;
            overflow: hidden;
        }
        
        [data-testid="stExpander"] > details {
            border: none !important;
        }

        /* Style dataframe container */
        [data-testid="stDataFrame"] {
            background: rgba(9, 9, 11, 0.5) !important;
            border: 1px solid rgba(255, 255, 255, 0.04) !important;
            border-radius: 12px !important;
            padding: 8px !important;
            box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.05) !important;
        }

        /* Slider Styling */
        .stSlider [data-baseweb="slider"] > div {
            background-color: rgba(255, 255, 255, 0.05) !important;
            height: 6px !important;
        }
        .stSlider [data-baseweb="slider"] [role="slider"] {
            background-color: #d4af37 !important;
            border: 2px solid #ffffff !important;
            box-shadow: 0 0 10px rgba(212, 175, 55, 0.6) !important;
            width: 18px !important;
            height: 18px !important;
            transition: transform 0.2s ease !important;
        }
        .stSlider [data-baseweb="slider"] [role="slider"]:hover {
            transform: scale(1.2) !important;
        }
        
        /* Slider text, ticks, min/max labels contrast overrides */
        .stSlider [data-testid="stWidgetLabel"],
        .stSlider [data-testid="stTickBarMin"],
        .stSlider [data-testid="stTickBarMax"],
        .stSlider [data-testid="stSliderTickBar"] div,
        .stSlider [data-testid="stSliderTickBar"] span,
        .stSlider [data-testid="stMarkdownContainer"] p {
            color: #cbd5e1 !important;
            font-weight: 500 !important;
        }
        
        /* Captions and Explanatory text contrast overrides */
        [data-testid="stCaptionContainer"],
        .stCaption,
        .stCaption p,
        .stCaption span,
        .stMarkdown p > sub,
        [data-testid="stMarkdownContainer"] caption,
        div.stCaption p {
            color: #94a3b8 !important;
            opacity: 1.0 !important;
            font-size: 0.88rem !important;
        }
        
        /* Tab panels */
        [data-testid="stTabBar"] {
            background-color: rgba(255, 255, 255, 0.02) !important;
            border-radius: 12px !important;
            padding: 4px !important;
            border: 1px solid rgba(255, 255, 255, 0.04) !important;
        }
        [data-testid="stTabBar"] button {
            color: #94a3b8 !important;
            font-family: 'Outfit', sans-serif !important;
            font-weight: 500 !important;
            border-radius: 8px !important;
            transition: all 400ms cubic-bezier(0.32, 0.72, 0, 1) !important;
        }
        [data-testid="stTabBar"] button[aria-selected="true"] {
            background: rgba(212, 175, 55, 0.08) !important;
            color: #d4af37 !important;
            font-weight: 600 !important;
        }

        /* ============================================================
           6. Divider Lines & Decorative Accents
           ============================================================ */
        hr {
            background: linear-gradient(to right, transparent, rgba(212, 175, 55, 0.3), transparent) !important;
            height: 1px !important;
            border: none !important;
            margin: 28px 0 !important;
        }

        /* Film grain noise overlay */
        .noise-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            content: "";
            opacity: 0.015;
            pointer-events: none;
            z-index: 99999;
            background: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
        }

        /* Premium console — shared glass-panel for page control expanders */
        .premium-console {
            background: rgba(15, 23, 42, 0.4);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }

        /* ============================================================
           Compliance Disclaimer & Banner / 合规免责声明与横幅
           ============================================================ */
        .compliance-disclaimer {
            background: linear-gradient(135deg, rgba(234, 179, 8, 0.06), rgba(234, 179, 8, 0.02));
            border-left: 3px solid rgba(234, 179, 8, 0.5);
            border-radius: 8px;
            padding: 16px 20px 12px 20px;
            margin-bottom: 20px;
        }
        .compliance-disclaimer .compliance-body {
            color: #94a3b8 !important;
            font-size: 0.88rem !important;
            line-height: 1.55 !important;
            margin-bottom: 8px;
            padding-left: 8px;
        }
        .compliance-disclaimer hr {
            border-color: rgba(234, 179, 8, 0.12) !important;
            margin: 12px 0 !important;
        }
        .compliance-banner {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0.02));
            border-left: 3px solid rgba(59, 130, 246, 0.4);
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 20px;
            color: #cbd5e1 !important;
            font-size: 0.88rem !important;
            line-height: 1.5 !important;
        }
        </style>
        <div class="noise-overlay"></div>
        """,
        unsafe_allow_html=True,
    )
