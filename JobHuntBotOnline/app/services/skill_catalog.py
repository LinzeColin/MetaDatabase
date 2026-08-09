from __future__ import annotations

import re
from collections import OrderedDict


SKILL_ALIASES: "OrderedDict[str, tuple[str, ...]]" = OrderedDict(
    {
        "Python": ("python",),
        "SQL": ("sql", "postgresql", "mysql", "sqlite", "t-sql"),
        "Excel": ("excel", "vlookup", "xlookup", "pivot table", "power query"),
        "Power BI": ("power bi", "powerbi", "dax"),
        "Tableau": ("tableau",),
        "R": (" r ", "r programming", "rstudio"),
        "Java": ("java",),
        "JavaScript": ("javascript", "typescript", "node.js", "nodejs"),
        "React": ("react", "next.js", "nextjs"),
        "AWS": ("aws", "amazon web services"),
        "Azure": ("azure",),
        "GCP": ("gcp", "google cloud"),
        "Docker": ("docker", "containerisation", "containerization"),
        "Kubernetes": ("kubernetes", "k8s"),
        "Git": (" git ", "github", "gitlab"),
        "REST API": ("rest api", "restful", "api integration"),
        "Data Analysis": ("data analysis", "data analytics", "analytical insights"),
        "Data Visualisation": ("data visualisation", "data visualization", "dashboarding"),
        "Statistics": ("statistics", "statistical analysis", "hypothesis testing"),
        "Machine Learning": ("machine learning", "ml model", "predictive model"),
        "Generative AI": ("generative ai", "large language model", "llm", "prompt engineering"),
        "Financial Modelling": ("financial modelling", "financial modeling", "three statement model"),
        "Valuation": ("valuation", "dcf", "discounted cash flow", "comparable company"),
        "Accounting": ("accounting", "financial reporting", "general ledger", "gaap", "ifrs"),
        "Corporate Finance": ("corporate finance", "capital structure", "capital budgeting"),
        "Investment Analysis": ("investment analysis", "equity research", "portfolio analysis"),
        "Risk Management": ("risk management", "risk assessment", "risk analytics"),
        "Audit": ("audit", "assurance", "internal controls"),
        "Compliance": ("compliance", "regulatory", "aml", "kyc"),
        "Econometrics": ("econometrics", "regression analysis", "time series"),
        "Forecasting": ("forecasting", "budgeting", "scenario analysis"),
        "Business Analysis": ("business analysis", "requirements gathering", "process mapping"),
        "Project Management": ("project management", "project delivery", "agile", "scrum"),
        "Product Management": ("product management", "product roadmap", "user stories"),
        "Operations": ("operations", "operational excellence", "process improvement"),
        "Supply Chain": ("supply chain", "procurement", "logistics", "inventory"),
        "Marketing": ("marketing", "campaign", "brand strategy", "go-to-market", "gtm"),
        "Sales": ("sales", "business development", "pipeline management"),
        "Customer Success": ("customer success", "account management", "client success"),
        "Research": ("research", "literature review", "market research"),
        "Stakeholder Management": ("stakeholder management", "stakeholder engagement"),
        "Communication": ("communication", "written and verbal", "presentation skills"),
        "Problem Solving": ("problem solving", "problem-solving", "critical thinking"),
        "Teamwork": ("teamwork", "collaboration", "cross-functional"),
        "Leadership": ("leadership", "led a team", "people management"),
        "Attention to Detail": ("attention to detail", "detail-oriented", "accuracy"),
        "Time Management": ("time management", "prioritisation", "prioritization"),
        "English": ("english",),
        "Mandarin": ("mandarin", "chinese language", "中文"),
        "Cantonese": ("cantonese",),
        "SAP": ("sap", "s/4hana"),
        "Salesforce": ("salesforce",),
        "Xero": ("xero",),
        "MYOB": ("myob",),
        "Bloomberg": ("bloomberg terminal", "bloomberg"),
        "Capital IQ": ("capital iq", "capiq"),
        "Alteryx": ("alteryx",),
        "Snowflake": ("snowflake",),
        "Databricks": ("databricks",),
        "Airflow": ("airflow",),
        "ETL": ("etl", "data pipeline", "data engineering"),
        "Cybersecurity": ("cybersecurity", "information security", "security controls"),
        "Cloudflare": ("cloudflare",),
        "Linux": ("linux", "unix"),
        "Bash": ("bash", "shell scripting"),
    }
)

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "our", "are", "will",
    "have", "has", "into", "using", "role", "team", "work", "working", "skills", "experience",
    "ability", "including", "within", "across", "about", "job", "position", "candidate", "company",
    "their", "they", "them", "who", "what", "where", "when", "which", "not", "but", "all",
    "a", "an", "to", "of", "in", "on", "at", "or", "as", "is", "be", "we", "it", "by",
}


def _normalized(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower()) + " "


def extract_skills(text: str) -> list[str]:
    haystack = _normalized(text)
    found: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(alias.lower() in haystack for alias in aliases):
            found.append(canonical)
    return found


def top_keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.&/-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for word in words:
        cleaned = word.strip(".-/&#")
        if len(cleaned) < 3 or cleaned in STOPWORDS or cleaned.isdigit():
            continue
        counts[cleaned] = counts.get(cleaned, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ranked[:limit]]
