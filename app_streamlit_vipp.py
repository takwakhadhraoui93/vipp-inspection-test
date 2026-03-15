import os
import ssl
import smtplib
import sqlite3
import unicodedata
from email.message import EmailMessage

import pandas as pd
import spacy
import streamlit as st


# =========================================================
# CONFIG APP
# =========================================================
st.set_page_config(page_title="Questionnaire VIPP", layout="wide")


def get_secret(name, default=""):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


SMTP_HOST = get_secret("SMTP_HOST")
SMTP_PORT = int(get_secret("SMTP_PORT", "465"))
SMTP_USER = get_secret("SMTP_USER")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD")
MAIL_FROM = get_secret("MAIL_FROM", SMTP_USER)

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin123")


# =========================================================
# NLP
# =========================================================
@st.cache_resource
def load_spacy():
    return spacy.load("fr_core_news_sm")


nlp = load_spacy()


def strip_accents(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return strip_accents(str(text).lower().strip())


def extract_lemmas(text: str):
    doc = nlp(normalize_text(text))
    lemmas = []
    for token in doc:
        if token.is_space or token.is_punct or token.is_stop:
            continue
        lemma = strip_accents(token.lemma_.lower().strip())
        if not lemma or lemma in {"etre", "avoir", "faire", "dire"}:
            continue
        lemmas.append(lemma)
    return lemmas


def analyze_justification_spacy(text: str, concept_dict: dict):
    lemmas = extract_lemmas(text)
    lemma_set = set(lemmas)

    found = []
    for concept, variants in concept_dict.items():
        variants_norm = {strip_accents(v.lower()) for v in variants}
        if lemma_set.intersection(variants_norm):
            found.append(concept)

    score = len(found)
    if score == 0:
        quality = "faible"
    elif score <= 2:
        quality = "moyenne"
    else:
        quality = "bonne"

    return {
        "score": score,
        "concepts": ", ".join(found),
        "quality": quality,
        "lemmas": ", ".join(sorted(lemma_set)),
    }


Q2_CONCEPT_DICT = {
    "profil": ["profil", "longitudinal", "rupture"],
    "appui": ["appui", "appuis"],
    "structure": ["structure", "structural", "tablier", "travée"],
    "gravite": ["grave", "critique", "danger", "alerte"],
}

Q8_CONCEPT_DICT = {
    "fissure": ["fissure", "fissuration", "longitudinale"],
    "precontrainte": ["precontrainte", "cable", "cables", "gaine"],
    "gravite": ["grave", "critique", "danger", "alerte"],
    "structure": ["structure", "porteur", "poutre"],
}

Q30_CONCEPT_DICT = {
    "beton": ["beton", "degradation", "desagregation"],
    "gravite": ["grave", "critique", "danger", "alerte"],
    "evolution": ["evolution", "aggravation", "important"],
    "structure": ["tablier", "ouvrage", "structure"],
}


# =========================================================
# BASE SQLITE
# =========================================================
conn = sqlite3.connect("inspecteurs.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS sessions_users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT,
    prenom TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS resultats(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT,
    prenom TEXT,
    email TEXT,
    score INTEGER,
    total INTEGER,
    taux_reussite REAL,
    profil TEXT,
    erreurs_critiques INTEGER,
    sous_estimation INTEGER,
    sur_estimation INTEGER,
    rapport TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()


# =========================================================
# QUESTIONS
# 3 questions avec justification : Q2, Q8, Q30
# =========================================================
QUESTIONS = [
    {
        "id": 1,
        "theme": "tablier",
        "title": "Question 1 – Comportement global du tablier",
        "text": "Vous observez une flèche longitudinale vers le bas sur l’ensemble d’une travée, accompagnée d’une diminution de la contreflèche.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 2,
        "theme": "tablier",
        "title": "Question 2 – Comportement global du tablier",
        "text": "Une rupture du profil longitudinal est visible au droit d’un appui.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
    },
    {
        "id": 3,
        "theme": "tablier",
        "title": "Question 3 – Comportement global du tablier",
        "text": "Un déhanché transversal de l’ensemble du tablier est observé.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 4,
        "theme": "fissures_poutres",
        "title": "Question 4 – Fissures des poutres",
        "text": "Une fissure verticale part de l’intrados de la poutre et remonte vers l’âme au centre de la travée.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 5,
        "theme": "fissures_poutres",
        "title": "Question 5 – Fissures des poutres",
        "text": "Des fissures obliques apparaissent près des appuis.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 6,
        "theme": "fissures_poutres",
        "title": "Question 6 – Fissures des poutres",
        "text": "Une fissure située à l’about de la poutre remonte depuis le talon.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 7,
        "theme": "fissures_poutres",
        "title": "Question 7 – Fissures des poutres",
        "text": "Une fissure courte apparaît à proximité d’un ancrage de câble de précontrainte.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 8,
        "theme": "precontrainte",
        "title": "Question 8 – Fissures des poutres",
        "text": "Une fissure longitudinale suit le tracé d’un câble de précontrainte sur une grande longueur.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
    },
    {
        "id": 9,
        "theme": "fissures_poutres",
        "title": "Question 9 – Fissures des poutres",
        "text": "Une fracture horizontale du talon de la poutre s’étend sur plusieurs mètres.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 10,
        "theme": "fissures_poutres",
        "title": "Question 10 – Fissures des poutres",
        "text": "Des fissures apparaissent à la jonction entre l’âme de la poutre et le hourdis.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 11,
        "theme": "defauts_poutres",
        "title": "Question 11 – Défauts des poutres",
        "text": "Un éclatement vertical de l’âme avec armatures apparentes est observé.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 12,
        "theme": "defauts_poutres",
        "title": "Question 12 – Défauts des poutres",
        "text": "Des épaufrures apparaissent sur la poutre au niveau des zones de levage.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 13,
        "theme": "defauts_poutres",
        "title": "Question 13 – Défauts des poutres",
        "text": "Le cachetage d’un ancrage de câble de précontrainte est décollé.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 14,
        "theme": "defauts_poutres",
        "title": "Question 14 – Défauts des poutres",
        "text": "Des lacunes de béton avec mise à nu d’armatures sont observées sur la poutre.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 15,
        "theme": "hourdis",
        "title": "Question 15 – Hourdis",
        "text": "Des fissures transversales apparaissent dans le hourdis au droit des câbles de précontrainte.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 16,
        "theme": "hourdis",
        "title": "Question 16 – Hourdis",
        "text": "Une fissuration oblique en arêtes de poisson apparaît près des abouts des poutres.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 17,
        "theme": "hourdis",
        "title": "Question 17 – Hourdis",
        "text": "Une fissure longitudinale apparaît au niveau d’une reprise de bétonnage entre poutre et hourdis.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 18,
        "theme": "hourdis",
        "title": "Question 18 – Hourdis",
        "text": "Des fissures nombreuses apparaissent dans le hourdis avec infiltration d’eau.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 19,
        "theme": "hourdis",
        "title": "Question 19 – Hourdis",
        "text": "Un éclatement du béton du hourdis avec armatures visibles est observé.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 20,
        "theme": "hourdis",
        "title": "Question 20 – Hourdis",
        "text": "Des traces de circulation d’eau apparaissent en sous-face du hourdis avec stalactites de calcite.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 21,
        "theme": "entretoises",
        "title": "Question 21 – Entretoises",
        "text": "Une fissure apparaît au droit d’une reprise de bétonnage dans une entretoise.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 22,
        "theme": "entretoises",
        "title": "Question 22 – Entretoises",
        "text": "Des fissures obliques apparaissent dans une entretoise.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 23,
        "theme": "entretoises",
        "title": "Question 23 – Entretoises",
        "text": "Un éclatement du béton d’une entretoise avec armatures visibles est observé.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 24,
        "theme": "beton",
        "title": "Question 24 – Défauts du béton",
        "text": "Des épaufrures apparaissent aux angles inférieurs d’une poutre suite à un choc.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 25,
        "theme": "beton",
        "title": "Question 25 – Défauts du béton",
        "text": "Des nids de cailloux sont observés dans une poutre.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 26,
        "theme": "beton",
        "title": "Question 26 – Défauts du béton",
        "text": "Des fuites de laitance apparaissent au niveau des joints de coffrage.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 27,
        "theme": "beton",
        "title": "Question 27 – Défauts du béton",
        "text": "Une ségrégation du béton est observée sur un parement de poutre.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 28,
        "theme": "beton",
        "title": "Question 28 – Défauts du béton",
        "text": "Un faïençage superficiel apparaît sur le béton du tablier.",
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
    },
    {
        "id": 29,
        "theme": "beton",
        "title": "Question 29 – Défauts du béton",
        "text": "Un maillage régulier de fissures apparaît dans le béton.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 30,
        "theme": "beton",
        "title": "Question 30 – Défauts du béton",
        "text": "Une désagrégation importante du béton est observée sur le tablier.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
    },
]

QUESTION_MAP = {q["id"]: q for q in QUESTIONS}


# =========================================================
# SESSION
# =========================================================
if "page" not in st.session_state:
    st.session_state.page = "home"

if "question" not in st.session_state:
    st.session_state.question = 1

if "answers" not in st.session_state:
    st.session_state.answers = {}

if "justifs" not in st.session_state:
    st.session_state.justifs = {}

if "result_saved" not in st.session_state:
    st.session_state.result_saved = False

if "mail_sent" not in st.session_state:
    st.session_state.mail_sent = False


# =========================================================
# HELPERS
# =========================================================
def answer_order(value: str) -> int:
    return {"Bénin": 1, "Moyen": 2, "Grave": 3}.get(value, 0)


def get_strengths_and_weaknesses(theme_percentages):
    strengths = []
    weaknesses = []

    for theme, value in theme_percentages.items():
        if value >= 75:
            strengths.append(theme)
        elif value < 50:
            weaknesses.append(theme)

    return strengths, weaknesses


def generate_recommendation(result_row):
    critical_errors = result_row.get("erreurs_critiques", 0)
    under = result_row.get("sous_estimation", 0)
    q2_quality = result_row.get("q2_qualite", "")
    q8_quality = result_row.get("q8_qualite", "")
    q30_quality = result_row.get("q30_qualite", "")

    if critical_errors >= 3:
        return "Une formation prioritaire sur l'identification des situations graves et des signaux d’alerte est recommandée."
    if under >= 5:
        return "Une sensibilisation au risque de sous-estimation des désordres structurels est recommandée."
    if q2_quality == "faible" or q8_quality == "faible" or q30_quality == "faible":
        return "Un renforcement du raisonnement technique écrit est recommandé sur les cas critiques."
    if result_row.get("taux_reussite", 0) >= 80:
        return "Le niveau est satisfaisant. Un maintien des acquis par retour d’expérience est recommandé."
    return "Une consolidation ciblée sur les thèmes les moins maîtrisés est recommandée."


def send_report_email(to_email: str, subject: str, body: str):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and MAIL_FROM):
        raise RuntimeError("Configuration SMTP incomplète.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def analyze_submission(nom: str, prenom: str, email: str):
    score = 0
    total = len(QUESTIONS)
    under_estimation = 0
    over_estimation = 0
    critical_errors = 0
    theme_scores = {}
    erreurs_details = []

    for q in QUESTIONS:
        qid = q["id"]
        user_answer = st.session_state.answers.get(qid, "")
        correct_answer = q["correct"]
        theme = q["theme"]
        criticality = q["critical"]

        if theme not in theme_scores:
            theme_scores[theme] = {"correct": 0, "total": 0}
        theme_scores[theme]["total"] += 1

        if user_answer == correct_answer:
            score += 1
            theme_scores[theme]["correct"] += 1
        else:
            u = answer_order(user_answer)
            c_ = answer_order(correct_answer)

            if u < c_:
                under_estimation += 1
                error_type = "sous-estimation"
            elif u > c_:
                over_estimation += 1
                error_type = "sur-estimation"
            else:
                error_type = "réponse invalide ou vide"

            if criticality == "high":
                critical_errors += 1

            erreurs_details.append(
                f"Q{qid}: répondu {user_answer or 'vide'} / attendu {correct_answer} ({error_type})"
            )

    q2_analysis = analyze_justification_spacy(st.session_state.justifs.get(2, ""), Q2_CONCEPT_DICT)
    q8_analysis = analyze_justification_spacy(st.session_state.justifs.get(8, ""), Q8_CONCEPT_DICT)
    q30_analysis = analyze_justification_spacy(st.session_state.justifs.get(30, ""), Q30_CONCEPT_DICT)

    theme_percentages = {}
    for theme, stats in theme_scores.items():
        pct = round((stats["correct"] / stats["total"]) * 100, 2) if stats["total"] > 0 else 0.0
        theme_percentages[theme] = pct

    if score >= 24 and critical_errors <= 1:
        profil = "Bon niveau global"
    elif critical_errors >= 3:
        profil = "Faiblesse sur les situations graves"
    elif under_estimation >= 5:
        profil = "Tendance à sous-estimer la gravité"
    elif over_estimation >= 5:
        profil = "Tendance à sur-estimer la gravité"
    else:
        profil = "Niveau intermédiaire"

    commentaire = (
        f"Score {score}/{total}. "
        f"Erreurs critiques : {critical_errors}. "
        f"Sous-estimations : {under_estimation}. "
        f"Sur-estimations : {over_estimation}. "
        f"Justification Q2 : {q2_analysis['quality']}. "
        f"Justification Q8 : {q8_analysis['quality']}. "
        f"Justification Q30 : {q30_analysis['quality']}."
    )

    result_row = {
        "nom": nom,
        "prenom": prenom,
        "email": email,
        "score": score,
        "total": total,
        "taux_reussite": round(score / total * 100, 2),
        "sous_estimation": under_estimation,
        "sur_estimation": over_estimation,
        "erreurs_critiques": critical_errors,
        "profil": profil,
        "commentaire_auto": commentaire,
        "details_erreurs": " | ".join(erreurs_details),
        "q2_nlp_score": q2_analysis["score"],
        "q2_concepts": q2_analysis["concepts"],
        "q2_qualite": q2_analysis["quality"],
        "q8_nlp_score": q8_analysis["score"],
        "q8_concepts": q8_analysis["concepts"],
        "q8_qualite": q8_analysis["quality"],
        "q30_nlp_score": q30_analysis["score"],
        "q30_concepts": q30_analysis["concepts"],
        "q30_qualite": q30_analysis["quality"],
        "theme_percentages": theme_percentages,
    }
    return result_row


def generate_report(result_row):
    strengths, weaknesses = get_strengths_and_weaknesses(result_row["theme_percentages"])

    strengths_text = ", ".join(strengths) if strengths else "Aucun point fort nettement dominant identifié."
    weaknesses_text = ", ".join(weaknesses) if weaknesses else "Aucune faiblesse majeure détectée."

    return f"""
RAPPORT INDIVIDUEL D'ÉVALUATION
================================

Employé : {result_row['prenom']} {result_row['nom']}
Email : {result_row['email']}

1. Résultat global
------------------
Score : {result_row['score']} / {result_row['total']}
Taux de réussite : {result_row['taux_reussite']} %
Profil : {result_row['profil']}

2. Analyse du jugement
----------------------
Sous-estimations : {result_row['sous_estimation']}
Sur-estimations : {result_row['sur_estimation']}
Erreurs critiques : {result_row['erreurs_critiques']}

3. Analyse des compétences
--------------------------
Points forts : {strengths_text}
Points faibles : {weaknesses_text}

6. Recommandation
-----------------
{generate_recommendation(result_row)}
""".strip()


# =========================================================
# PAGE HOME
# =========================================================
if st.session_state.page == "home":
    st.title("Questionnaire de validation des connaissances")
    st.subheader("Inspecteurs d’ouvrages d’art – Ponts VIPP")

    menu = st.sidebar.radio("Menu", ["Connexion", "Admin"])

    if menu == "Connexion":
        st.subheader("Connexion employé")
        nom = st.text_input("Nom")
        prenom = st.text_input("Prénom")
        email = st.text_input("Adresse e-mail")

        if st.button("Continuer"):
            if not nom or not prenom or not email:
                st.error("Tous les champs sont obligatoires.")
            elif "@" not in email:
                st.error("Adresse e-mail invalide.")
            else:
                st.session_state.nom = nom
                st.session_state.prenom = prenom
                st.session_state.email = email
                st.session_state.page = "accueil"

                c.execute(
                    "INSERT INTO sessions_users(nom, prenom, email) VALUES (?, ?, ?)",
                    (nom, prenom, email),
                )
                conn.commit()

                st.rerun()

    elif menu == "Admin":
        st.subheader("Admin - Tableau des résultats")
        password = st.text_input("Mot de passe admin", type="password")
        if password == ADMIN_PASSWORD:
            df_sessions = pd.read_sql_query(
                "SELECT nom, prenom, email, created_at FROM sessions_users ORDER BY created_at DESC",
                conn,
            )
            df_results = pd.read_sql_query(
                """
                SELECT id, nom, prenom, email, score, total, taux_reussite, profil,
                       erreurs_critiques, created_at, rapport
                FROM resultats
                ORDER BY created_at DESC
                """,
                conn,
            )

            st.markdown("### Connexions")
            st.dataframe(df_sessions, use_container_width=True)

            st.markdown("### Résultats")
            st.dataframe(
                df_results.drop(columns=["rapport"]),
                use_container_width=True
            )

            if not df_results.empty:
                st.markdown("### Consulter un rapport")
                selected_id = st.selectbox(
                    "Choisir un résultat",
                    df_results["id"].tolist(),
                    format_func=lambda x: (
                        f"ID {x} - "
                        f"{df_results[df_results['id'] == x]['prenom'].iloc[0]} "
                        f"{df_results[df_results['id'] == x]['nom'].iloc[0]} - "
                        f"Score {df_results[df_results['id'] == x]['score'].iloc[0]}/"
                        f"{df_results[df_results['id'] == x]['total'].iloc[0]}"
                    )
                )

                selected_row = df_results[df_results["id"] == selected_id].iloc[0]

                with st.expander("Voir le rapport complet", expanded=True):
                    st.text(selected_row["rapport"])

                st.download_button(
                    "Télécharger le rapport sélectionné",
                    data=selected_row["rapport"].encode("utf-8"),
                    file_name=f"rapport_{selected_row['nom']}_{selected_row['prenom']}.txt",
                    mime="text/plain",
                )


# =========================================================
# PAGE ACCUEIL UTILISATEUR
# =========================================================
elif st.session_state.page == "accueil":
    st.title(f"Bienvenue {st.session_state.prenom} {st.session_state.nom}")
    st.write(f"Email : {st.session_state.email}")
    st.write("Répondre pour chaque situation :")
    st.write("🟥 Grave – Alerter immédiatement")
    st.write("🟧 Moyen – À surveiller")
    st.write("🟩 Bénin – Pas d’alerte nécessaire")

    if st.button("Lancer le test"):
        st.session_state.page = "quiz"
        st.session_state.question = 1
        st.session_state.answers = {}
        st.session_state.justifs = {}
        st.session_state.result_saved = False
        st.session_state.mail_sent = False
        st.rerun()

    if st.button("Déconnexion"):
        st.session_state.page = "home"
        st.rerun()


# =========================================================
# PAGE QUIZ
# =========================================================
elif st.session_state.page == "quiz":
    qid = st.session_state.question
    q = QUESTION_MAP[qid]

    st.title(f"Question {qid} / 30")
    st.progress(qid / 30)
    st.markdown(f"### {q['title']}")
    st.write(q["text"])

    options = ["Grave", "Moyen", "Bénin"]
    current_answer = st.session_state.answers.get(qid, "Grave")

    selected = st.radio(
        "Choisir la gravité",
        options,
        index=options.index(current_answer),
        key=f"q_{qid}_radio"
    )

    st.session_state.answers[qid] = selected

    if q["requires_justification"]:
        justif_default = st.session_state.justifs.get(qid, "")
        justif = st.text_area(
            "Justification obligatoire",
            value=justif_default,
            key=f"q_{qid}_justif",
            placeholder="Expliquez brièvement votre diagnostic."
        )
        st.session_state.justifs[qid] = justif

    col1, col2 = st.columns(2)

    if qid > 1:
        if col1.button("Précédent", key=f"prev_{qid}"):
            st.session_state.question -= 1
            st.rerun()

    if col2.button("Suivant" if qid < 30 else "Terminer", key=f"next_{qid}"):
        if q["requires_justification"] and not st.session_state.justifs.get(qid, "").strip():
            st.error("La justification est obligatoire pour cette question.")
        else:
            if qid < 30:
                st.session_state.question += 1
                st.rerun()
            else:
                st.session_state.page = "result"
                st.rerun()


# =========================================================
# PAGE RESULTAT
# =========================================================
elif st.session_state.page == "result":
    st.title("Résultat du test")

    result_row = analyze_submission(
        st.session_state.nom,
        st.session_state.prenom,
        st.session_state.email,
    )
    report_text = generate_report(result_row)

    st.subheader(f"Score : {result_row['score']} / {result_row['total']}")

    if result_row["score"] >= 24:
        st.success("Employé apte à sortir en terrain")
    else:
        st.error("Employé non apte – formation requise")

    st.write(f"**Profil :** {result_row['profil']}")
    st.write(f"**Erreurs critiques :** {result_row['erreurs_critiques']}")
    st.write(f"**Sous-estimations :** {result_row['sous_estimation']}")
    st.write(f"**Sur-estimations :** {result_row['sur_estimation']}")

    with st.expander("Voir le rapport complet", expanded=True):
        st.text(report_text)

    st.download_button(
        "Télécharger le rapport",
        data=report_text.encode("utf-8"),
        file_name=f"rapport_{st.session_state.nom}_{st.session_state.prenom}.txt",
        mime="text/plain",
    )

    if not st.session_state.result_saved:
        c.execute(
            """
            INSERT INTO resultats(nom, prenom, email, score, total, taux_reussite, profil,
                                  erreurs_critiques, sous_estimation, sur_estimation, rapport)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                st.session_state.nom,
                st.session_state.prenom,
                st.session_state.email,
                result_row["score"],
                result_row["total"],
                result_row["taux_reussite"],
                result_row["profil"],
                result_row["erreurs_critiques"],
                result_row["sous_estimation"],
                result_row["sur_estimation"],
                report_text,
            ),
        )
        conn.commit()
        st.session_state.result_saved = True

    if not st.session_state.mail_sent:
        try:
            send_report_email(
                to_email=st.session_state.email,
                subject="Votre rapport d’évaluation VIPP",
                body=report_text,
            )
            st.success(f"Le rapport a été envoyé à {st.session_state.email}.")
            st.session_state.mail_sent = True
        except Exception as e:
            st.warning(f"Rapport généré, mais l’envoi du mail a échoué : {e}")

    if st.button("Retour accueil"):
        st.session_state.page = "accueil"
        st.rerun()
