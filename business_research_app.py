import os
import re
import json
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from ddgs import DDGS

APP_TITLE = "Business Research & Competitor Intelligence"

st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title("📊 Business Research & Competitor Intelligence")
st.caption("Python + Streamlit | ওয়েব রিসার্চ, কোম্পানি প্রোফাইল, কম্পিটিটর ও SWOT বিশ্লেষণ")

st.info(
    "গুরুত্বপূর্ণ: এটি একটি research assistant / MVP। ওয়েবের সব তথ্য স্ক্র্যাপ করা সম্ভব বা বৈধ নয়। "
    "শুধু প্রকাশ্য পৃষ্ঠা, অনুমোদিত API এবং সাইটের Terms/robots.txt মেনে ব্যবহার করুন। "
    "রিপোর্টের প্রতিটি দাবি মূল উৎসে যাচাই করুন।"
)

with st.sidebar:
    st.header("সেটিংস")
    max_results = st.slider("প্রতি সার্চে ফলাফল", 3, 10, 6)
    max_pages = st.slider("বিশ্লেষণের জন্য পৃষ্ঠা", 2, 8, 5)
    timeout = st.slider("প্রতি পৃষ্ঠার timeout (সেকেন্ড)", 5, 25, 12)
    st.markdown("---")
    st.write("ঐচ্ছিক AI বিশ্লেষণ")
    use_ai = st.checkbox("OpenAI API দিয়ে বিশ্লেষণ", value=bool(os.getenv("OPENAI_API_KEY")))
    st.caption("AI চালাতে OPENAI_API_KEY environment variable সেট করুন।")

query = st.text_input(
    "কোন ব্যবসা, কোম্পানি বা বাজার নিয়ে গবেষণা করবেন?",
    placeholder="যেমন: Bangladesh tractor spare parts market / Tesla / online grocery business",
)
region = st.text_input("দেশ / অঞ্চল (ঐচ্ছিক)", value="Bangladesh")
industry = st.text_input("ইন্ডাস্ট্রি বা নির্দিষ্ট বিষয় (ঐচ্ছিক)", placeholder="যেমন: pricing, competitors, suppliers")
seed_urls = st.text_area(
    "নির্দিষ্ট ওয়েবসাইট URL (ঐচ্ছিক; প্রতি লাইনে একটি)",
    placeholder="https://example.com\nhttps://competitor.com",
)
run = st.button("🔎 Market Research চালান", type="primary", use_container_width=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BusinessResearchAssistant/1.0; +https://github.com/)"
}

def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()

def search_web(q, limit=6):
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(q, max_results=limit):
                results.append({
                    "title": clean_text(r.get("title", "")),
                    "url": r.get("href", ""),
                    "snippet": clean_text(r.get("body", "")),
                })
    except Exception as e:
        st.warning(f"ওয়েব সার্চ সাময়িকভাবে ব্যর্থ হয়েছে: {e}")
    return results

def fetch_page(url, timeout_s=12):
    """Fetch a public page only. Avoid login pages, paywalls, and restricted endpoints."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {"url": url, "status": "invalid_url", "title": "", "text": ""}
        response = requests.get(url, headers=HEADERS, timeout=timeout_s)
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400:
            return {"url": url, "status": f"http_{response.status_code}", "title": "", "text": ""}
        if "text/html" not in content_type:
            return {"url": url, "status": "not_html", "title": "", "text": ""}
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            tag.decompose()
        title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
        description = ""
        meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta:
            description = clean_text(meta.get("content", ""))
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = clean_text(main.get_text(" ", strip=True))
        text = (description + " " + text).strip()
        return {"url": url, "status": "ok", "title": title, "text": text[:12000]}
    except Exception as e:
        return {"url": url, "status": f"error: {type(e).__name__}", "title": "", "text": ""}

def unique_results(results):
    seen, out = set(), []
    for item in results:
        url = item.get("url", "").split("#")[0].rstrip("/")
        if url and url not in seen:
            seen.add(url)
            item["url"] = url
            out.append(item)
    return out

def heuristic_analysis(topic, region_name, results, pages):
    all_text = " ".join(
        [f"{r.get('title','')} {r.get('snippet','')}" for r in results] +
        [f"{p.get('title','')} {p.get('text','')[:2500]}" for p in pages if p.get("status") == "ok"]
    ).lower()
    competitor_terms = ["competitor", "alternative", "market share", "pricing", "price", "review",
                        "features", "customer", "product", "service", "revenue", "growth"]
    found = [term for term in competitor_terms if term in all_text]
    sources = [r for r in results if r.get("url")]
    return {
        "topic": topic,
        "region": region_name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": (
            f"'{topic}' বিষয়ে {region_name} কেন্দ্রিক প্রাথমিক তথ্য সংগ্রহ করা হয়েছে। "
            "এটি স্বয়ংক্রিয় প্রাথমিক স্ক্যান—বাজারের আকার, বিক্রয়, মার্কেট শেয়ার বা আর্থিক ফলাফল "
            "নির্ভরযোগ্যভাবে নির্ধারণ করতে আলাদা যাচাইকৃত ডেটা প্রয়োজন।"
        ),
        "opportunities": [
            "গ্রাহকের অপূর্ণ চাহিদা ও কম-সার্ভিসড সেগমেন্ট খুঁজুন।",
            "প্রতিদ্বন্দ্বীদের মূল্য, ডেলিভারি, ওয়ারেন্টি ও বিক্রয়োত্তর সেবা তুলনা করুন।",
            "সরকারি পরিসংখ্যান, বার্ষিক প্রতিবেদন ও শিল্প সমিতির ডেটা দিয়ে বাজারের আকার যাচাই করুন."
        ],
        "risks": [
            "ওয়েব সার্চের ফলাফল অসম্পূর্ণ বা পুরোনো হতে পারে।",
            "অনেক কোম্পানি বাজারের শেয়ার/আয় প্রকাশ করে না।",
            "স্ক্র্যাপ করা পৃষ্ঠার তথ্য ভুল, প্রচারণামূলক বা প্রাসঙ্গিকতার বাইরে হতে পারে।"
        ],
        "terms_found": found,
        "sources": sources,
        "ai_used": False
    }

def openai_analysis(topic, region_name, industry_name, results, pages):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY পাওয়া যায়নি।")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    evidence = []
    for r in results:
        evidence.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("snippet", "")
        })
    for p in pages:
        if p.get("status") == "ok":
            evidence.append({
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "text_excerpt": p.get("text", "")[:3000]
            })
    prompt = f"""
তুমি একজন সতর্ক market research analyst। বাংলায় রিপোর্ট লেখো।
বিষয়: {topic}
অঞ্চল: {region_name}
অতিরিক্ত ফোকাস: {industry_name or 'সাধারণ ব্যবসায়িক বিশ্লেষণ'}
নিচের evidence-ই ব্যবহার করো। প্রমাণ ছাড়া তথ্য বানাবে না। তথ্য না থাকলে 'ডেটা পাওয়া যায়নি' বলো।
প্রতিটি গুরুত্বপূর্ণ দাবির সঙ্গে [S1], [S2] ইত্যাদি source label দাও; শেষে Sources তালিকায় label ও URL দাও।
কভার করো:
1) Executive summary
2) Market/customer segments এবং demand signals
3) Competitor comparison: শক্তি, দুর্বলতা, positioning, pricing/features (প্রমাণ থাকলেই)
4) SWOT
5) সম্ভাব্য সুযোগ ও ঝুঁকি
6) আরও কোন ডেটা সংগ্রহ করতে হবে
7) 30-day validation plan
স্পষ্টভাবে আলাদা করো: source-এ পাওয়া তথ্য বনাম অনুমান। বাজারের আকার/মার্কেট শেয়ার অনুমান করে লিখবে না।
Evidence JSON:
{json.dumps(evidence, ensure_ascii=False)[:24000]}
"""
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt
    )
    return response.output_text

if run:
    if not query.strip():
        st.error("প্রথমে ব্যবসা, কোম্পানি বা বাজারের নাম লিখুন।")
        st.stop()

    with st.spinner("ওয়েব সার্চ ও প্রকাশ্য পৃষ্ঠা সংগ্রহ করা হচ্ছে..."):
        search_queries = [
            f"{query} {region} market overview",
            f"{query} {region} competitors pricing products",
            f"{query} {region} company annual report customers",
        ]
        if industry.strip():
            search_queries.append(f"{query} {region} {industry}")
        results = []
        for q in search_queries:
            results.extend(search_web(q, max_results))
        results = unique_results(results)

        urls = [x.strip() for x in seed_urls.splitlines() if x.strip()]
        for r in results:
            if r["url"] and len(urls) < max_pages:
                urls.append(r["url"])
        urls = list(dict.fromkeys(urls))[:max_pages]
        pages = [fetch_page(u, timeout) for u in urls]

    st.success(f"সংগ্রহ সম্পন্ন: {len(results)}টি সার্চ ফলাফল, {sum(p['status']=='ok' for p in pages)}টি HTML পৃষ্ঠা সফলভাবে পড়া হয়েছে।")

    tab1, tab2, tab3, tab4 = st.tabs(["সারসংক্ষেপ", "সার্চ ফলাফল", "পৃষ্ঠার তথ্য", "রিপোর্ট ডাউনলোড"])
    with tab1:
        analysis = heuristic_analysis(query, region, results, pages)
        if use_ai:
            try:
                with st.spinner("AI দিয়ে প্রমাণ-ভিত্তিক রিপোর্ট তৈরি হচ্ছে..."):
                    analysis["ai_report"] = openai_analysis(query, region, industry, results, pages)
                    analysis["ai_used"] = True
                st.markdown(analysis["ai_report"])
            except Exception as e:
                st.error(f"AI রিপোর্ট তৈরি করা যায়নি: {e}")
                st.markdown(f"**প্রাথমিক সারসংক্ষেপ:** {analysis['summary']}")
        else:
            st.subheader("প্রাথমিক সারসংক্ষেপ")
            st.write(analysis["summary"])
            st.subheader("সম্ভাব্য সুযোগ")
            for item in analysis["opportunities"]:
                st.write("• " + item)
            st.subheader("ঝুঁকি ও সীমাবদ্ধতা")
            for item in analysis["risks"]:
                st.write("• " + item)
            st.caption("AI রিপোর্টের জন্য sidebar-এ OpenAI API ব্যবহার চালু করুন এবং OPENAI_API_KEY সেট করুন।")

        st.subheader("পরবর্তী গবেষণার অগ্রাধিকার")
        st.write("১) সরকারি/শিল্প-সমিতির বাজার ডেটা  ২) কোম্পানির বার্ষিক প্রতিবেদন  ৩) গ্রাহক সাক্ষাৎকার  ৪) বাস্তব মূল্য ও বিক্রয় যাচাই")

    with tab2:
        if results:
            df = pd.DataFrame(results)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("সার্চ ফলাফল CSV ডাউনলোড", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name="search_results.csv", mime="text/csv")
        else:
            st.warning("সার্চ ফলাফল পাওয়া যায়নি। অন্য শব্দ দিয়ে চেষ্টা করুন।")

    with tab3:
        for p in pages:
            with st.expander(f"{p.get('title') or p['url']} — {p['status']}"):
                st.write(p["url"])
                st.write(p.get("text", "")[:5000] or "পাঠযোগ্য টেক্সট পাওয়া যায়নি।")

    with tab4:
        report = {
            "topic": query,
            "region": region,
            "generated_at": datetime.now().isoformat(timespec="minutes"),
            "search_results": results,
            "pages": pages,
        }
        if "analysis" in locals() and analysis.get("ai_report"):
            report["ai_report"] = analysis["ai_report"]
        st.download_button(
            "সম্পূর্ণ গবেষণা JSON ডাউনলোড",
            json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="business_research_report.json",
            mime="application/json"
        )
        if "analysis" in locals() and analysis.get("ai_report"):
            st.download_button(
                "AI রিপোর্ট TXT ডাউনলোড",
                analysis["ai_report"].encode("utf-8"),
                file_name="business_research_report.txt",
                mime="text/plain"
            )

st.markdown("---")
st.caption("পরামর্শ: এই MVP-তে public web search + public HTML page extraction আছে। লগইন-সুরক্ষিত সাইট, paywall, CAPTCHA bypass, ব্যক্তিগত তথ্য সংগ্রহ বা সীমাবদ্ধ API scraping করবেন না।")
