import os
import ssl
import smtplib
import sqlite3
import json
from email.message import EmailMessage

import urllib.request
import pandas as pd
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


SMTP_HOST      = get_secret("SMTP_HOST")
SMTP_PORT      = int(get_secret("SMTP_PORT", "465"))
SMTP_USER      = get_secret("SMTP_USER")
SMTP_PASSWORD  = get_secret("SMTP_PASSWORD")
MAIL_FROM      = get_secret("MAIL_FROM", SMTP_USER)
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin123")
GEMINI_KEY = get_secret("GEMINI_API_KEY")

# Pondération par criticité
WEIGHTS = {"high": 3, "medium": 2, "low": 1}
MAX_WEIGHTED_SCORE = sum(WEIGHTS[q["critical"]] for q in []) # calculé plus bas


# =========================================================
# BASE SQLITE
# =========================================================
conn = sqlite3.connect("inspecteurs.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS sessions_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT, prenom TEXT, email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS resultats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT, prenom TEXT, email TEXT,
        score_brut INTEGER, score_pondere INTEGER, score_pondere_max INTEGER,
        taux_reussite REAL, aptitude TEXT, profil TEXT,
        score_danger REAL, score_precision REAL, score_justifications REAL,
        erreurs_critiques INTEGER, sous_estimation INTEGER, sur_estimation INTEGER,
        rapport TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()


# =========================================================
# QUESTIONS
# =========================================================
QUESTIONS = [
    # --- POUTRES ---
    {"id": 1,  "theme": "poutres",                  "title": "Question 1",
     "text": "Fissure(s) régnant sur une hauteur pouvant atteindre et dépasser les deux tiers de la hauteur de la poutre, la poutre présentant par ailleurs une cambrure trop faible, voire nulle et même négative.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},

    {"id": 2,  "theme": "poutres",                  "title": "Question 2",
     "text": "Fissuration avec éclatement vertical d'une âme, de type IX, au droit des armatures transversales, due à un enrobage insuffisant de celles-ci, sans trace de rouille ni éclatement du béton.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 3,  "theme": "poutres",                  "title": "Question 3",
     "text": "Fissure(s) longitudinale(s) de type V, suivant le tracé d'un câble sur tout ou partie de sa longueur, le plus souvent en zone de mi-portée, sèche(s) et fine(s) le long d'un seul câble, d'ouverture inférieure à 0,3 mm.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 4,  "theme": "poutres",                  "title": "Question 4",
     "text": "Fracture horizontale du talon de type VII, pouvant régner sur plusieurs mètres dans la partie centrale de la travée, pouvant être accompagnée d'un rejet horizontal, due à une ou plusieurs des causes cumulées suivantes : cadres de couture de talons insuffisants, effet de poussée dû au gel de l'eau circulant dans des câbles mal injectés, poussée d'expansion par la rouille due à la corrosion d'armatures passives, des conduits et peut-être même des câbles de précontrainte.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},

    {"id": 5,  "theme": "poutres",                  "title": "Question 5",
     "text": "Décollements des cachetages des ancrages des câbles de précontrainte longitudinale, avec venue d'eau et/ou accompagnés d'efflorescences et/ou avec traces de rouille, à la limite ancrage ou éléments de câble visibles, en présence concomitante de fissures de type I (Q.1) et II (Q.6).",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},

    {"id": 6,  "theme": "poutres",                  "title": "Question 6",
     "text": "Fissure(s) oblique(s) de type II, proche(s) des zones sur appui, parfois combinée(s) avec des fissures de type I, due(s) à l'effet excessif combiné du moment fléchissant et de l'effort tranchant et/ou à une perte de précontrainte.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},

    {"id": 7,  "theme": "poutres",                  "title": "Question 7",
     "text": "Fissures à la jonction entre l'âme et le hourdis ou le talon, de type VIII, d'ouverture inférieure à 0,3 mm ou avec venue d'eau, dues au retrait gêné de l'âme par les coffrages laissés trop longtemps en place et/ou à une insuffisance d'armatures de couture entre d'une part le hourdis et d'autre part le talon.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 8,  "theme": "poutres",                  "title": "Question 8",
     "text": "Épaufrures du béton aux angles inférieurs d'une poutre, résultant de chocs lors des opérations de manutention à la construction et/ou aux chocs de véhicules hors gabarit circulant sur la voie franchie, sans mise à nu d'armature.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": False, "alerte": False},

    {"id": 9,  "theme": "poutres",                  "title": "Question 9",
     "text": "Lacunes de béton en sous-face d'un talon de poutre à mi-travée, là où les armatures passives et actives sont les plus nombreuses, avec réduction des sections des armatures actives et/ou rupture de certaines d'entre elles, dues à un défaut de mise en œuvre du béton (vibrations insuffisantes, densité d'armatures importante) et/ou à une mauvaise formulation du béton.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": False, "alerte": True},

    {"id": 10, "theme": "poutres",                  "title": "Question 10",
     "text": "Fissure(s) localisée(s), épaufrures apparaissant lors des phases de manutention au droit des zones de levage, de type X, risquant de compromettre (fissuration importante, éclatements localisés importants) la résistance locale de la poutre.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},

    # --- HOURDIS INTERMÉDIAIRES ---
    {"id": 11, "theme": "hourdis_intermediaires",   "title": "Question 11",
     "text": "Fissuration oblique en « arêtes de poisson » près des abouts des poutres, de type XII, due à l'insuffisance de couture du hourdis sous l'effet de la diffusion de précontrainte et de l'effort tranchant, fines et sèches.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 12, "theme": "hourdis_intermediaires",   "title": "Question 12",
     "text": "Fissures longitudinales de type XIV, dues à une insuffisance de résistance ou à des efforts appliqués plus importants que prévus et/ou à l'effet de câbles de précontrainte transversale (câbles mal excentrés, poussée au vide), nombreuses, avec venue d'eau, dans le cas d'un hourdis précontraint transversalement avec traces de corrosion.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},

    {"id": 13, "theme": "hourdis_intermediaires",   "title": "Question 13",
     "text": "Éclatement, décollement du béton de type XV, localisés, avec éclatements par plaques de certaines zones du hourdis, sans réduction notable des sections des armatures apparentes et/ou, pour les hourdis précontraints, avec mise à nu des armatures actives sans réduction notable de leurs sections.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 14, "theme": "hourdis_intermediaires",   "title": "Question 14",
     "text": "Traces de circulation d'eau à travers le hourdis intermédiaire, liées à un défaut d'étanchéité en extrados, dues à l'absence totale ou partielle de chape d'étanchéité et/ou à des défauts de mise en œuvre de la chape, notamment aux raccordements sur les contre-bordures, les avaloirs, les joints de chaussée.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": False, "alerte": False},

    # --- HOURDIS EN ENCORBELLEMENT ---
    {"id": 15, "theme": "hourdis_encorbellement",   "title": "Question 15",
     "text": "Fissures de type XVII, transversales, réparties sur toute la longueur de l'encorbellement, dues au retrait gêné du béton de l'encorbellement coulé postérieurement à la poutre de rive, avec venue d'eau et/ou accompagnées d'efflorescences.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 16, "theme": "hourdis_encorbellement",   "title": "Question 16",
     "text": "Fissuration oblique en « arêtes de poisson » près des abouts des poutres, de type XX, due à l'insuffisance d'armatures de couture du hourdis sous l'effet de la diffusion de précontrainte et de l'effort tranchant, avec venue d'eau et coulures de rouille.",
     "correct": "Grave",  "critical": "high",   "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 17, "theme": "hourdis_encorbellement",   "title": "Question 17",
     "text": "Décollements des cachetages des ancrages des câbles de précontrainte transversale, secs, dus à une mauvaise adhérence du matériau de cachetage et/ou à un retrait excessif lors de la mise en œuvre du cachetage.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": False, "alerte": False},

    # --- ENTRETOISES ---
    {"id": 18, "theme": "entretoises",              "title": "Question 18",
     "text": "Fissurations obliques diverses de type XXII, verticales ou inclinées, sur entretoise en béton armé, dues à l'application d'efforts dissymétriques lors des phasages de mise en tension des poutres et du bétonnage du tablier et/ou à une insuffisante résistance aux effets de la flexion transversale, avec fissure(s) d'ouverture supérieure à 0,6 mm.",
     "correct": "Grave",  "critical": "high",   "requires_justification": False, "has_image": True,  "alerte": False},

    {"id": 19, "theme": "entretoises",              "title": "Question 19",
     "text": "Éclatement localisé de béton avec mise à nu d'armature(s) de type XXIII, dans l'angle inférieur d'une entretoise, dû à la poussée exercée par l'oxydation des armatures sur le béton d'enrobage, sans réduction notable des sections des armatures passives apparentes.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},

    # --- DÉFAUTS DU MATÉRIAU BÉTON ---
    {"id": 20, "theme": "defauts_beton",            "title": "Question 20",
     "text": "Efflorescences et stalactites sèches résultant de l'entraînement de la chaux contenue dans le béton par les circulations d'eaux internes et de son dépôt sous forme de calcite en parement.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": False, "alerte": False},
]

QUESTION_MAP = {q["id"]: q for q in QUESTIONS}
MAX_WEIGHTED_SCORE = sum(WEIGHTS[q["critical"]] for q in QUESTIONS)

SECTION_LABELS = {
    "poutres": "Poutres",
    "hourdis_intermediaires": "Hourdis intermédiaires",
    "hourdis_encorbellement": "Hourdis en encorbellement",
    "entretoises": "Entretoises",
    "defauts_beton": "Défauts du matériau béton",
}

QUESTION_IMAGES = {
    qid: f"images/Image{qid}.png"
    for qid in [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 15, 16, 18, 19]
}


# =========================================================
# SESSION
# =========================================================
for key, default in [
    ("page", "home"), ("question", 1), ("answers", {}),
    ("justifs", {}), ("result_saved", False), ("mail_sent", False),
    ("ai_analysis", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# =========================================================
# HELPERS
# =========================================================
def answer_order(v):
    return {"Bénin": 1, "Moyen": 2, "Grave": 3}.get(v, 0)


def call_gemini(prompt: str) -> str:
    """Appel à l'API Gemini (Google) — gratuit jusqu'à 1500 req/jour."""
    if not GEMINI_KEY:
        return "⚠️ Clé API Gemini non configurée."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}]
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"⚠️ Erreur Gemini : {e}"


def analyze_justifications_with_ai(justifs: dict) -> dict:
    """
    Envoie toutes les justifications à Claude et récupère une analyse structurée en JSON.
    """
    justif_questions = {q["id"]: q for q in QUESTIONS if q["requires_justification"]}

    justif_block = ""
    for qid, q in justif_questions.items():
        texte = justifs.get(qid, "").strip() or "(aucune justification fournie)"
        justif_block += f"\n---\nQuestion {qid} — {q['theme']} (désordre : {q['correct']}) :\n{q['text']}\nJustification de l'inspecteur : {texte}\n"

    prompt = f"""
Tu es un expert en inspection des ouvrages d'art (ponts VIPP - poutres précontraintes par post-tension).
Un inspecteur a répondu à un test de compétences IQOA et fourni des justifications pour les questions critiques.

Analyse chaque justification selon ces critères :
1. Pertinence technique : l'inspecteur a-t-il identifié la bonne cause du désordre ?
2. Complétude : a-t-il mentionné les éléments clés (mécanisme, conséquence, urgence) ?
3. Score de 0 à 3 (0=absente ou hors sujet, 1=partielle, 2=correcte, 3=excellente)

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après, avec ce format exact :
{{
  "justifications": {{
    "1": {{"score": 0, "commentaire": "..."}},
    "4": {{"score": 0, "commentaire": "..."}},
    "5": {{"score": 0, "commentaire": "..."}},
    "6": {{"score": 0, "commentaire": "..."}},
    "9": {{"score": 0, "commentaire": "..."}},
    "12": {{"score": 0, "commentaire": "..."}}
  }},
  "score_moyen": 0.0,
  "synthese": "..."
}}

Voici les justifications à analyser :
{justif_block}
"""
    raw = call_gemini(prompt)
    try:
        return json.loads(raw)
    except Exception:
        return {"justifications": {}, "score_moyen": 0.0, "synthese": raw}


def generate_ai_recommendation(result_data: dict) -> str:
    """Génère une recommandation personnalisée via Claude."""
    erreurs = result_data.get("details_erreurs", "Aucune erreur.")
    synthese_justifs = result_data.get("synthese_justifs", "")

    prompt = f"""
Tu es un expert formateur en inspection des ouvrages d'art (ponts VIPP).
Voici les résultats d'un inspecteur au test de compétences IQOA :

- Score brut : {result_data['score_brut']} / {result_data['total']}
- Score pondéré : {result_data['score_pondere']} / {result_data['score_pondere_max']} (questions Alerte = 3pts, Moyen = 2pts, Bénin = 1pt)
- Taux de réussite : {result_data['taux_reussite']} %
- Aptitude : {result_data['aptitude']}
- Score détection danger (questions Alerte) : {result_data['score_danger']} %
- Score précision jugement : {result_data['score_precision']} %
- Score qualité justifications : {result_data['score_justifications']} / 3
- Sous-estimations : {result_data['sous_estimation']}
- Sur-estimations : {result_data['sur_estimation']}
- Erreurs critiques : {result_data['erreurs_critiques']}
- Détail des erreurs : {erreurs}
- Synthèse des justifications : {synthese_justifs}

Rédige un rapport de recommandation personnalisé en français, structuré ainsi :
1. Synthèse du profil (2-3 phrases)
2. Points forts identifiés
3. Points faibles et axes d'amélioration prioritaires
4. Recommandation de formation concrète et adaptée au niveau

Sois précis, bienveillant et constructif. Maximum 300 mots.
"""
    return call_gemini(prompt)


def analyze_submission(nom, prenom, email):
    score_brut = 0
    score_pondere = 0
    total = len(QUESTIONS)
    under_est = 0
    over_est = 0
    critical_errors = 0
    high_correct = 0
    high_total = 0
    erreurs_details = []

    for q in QUESTIONS:
        qid = q["id"]
        user_ans = st.session_state.answers.get(qid, "Grave")
        correct = q["correct"]
        w = WEIGHTS[q["critical"]]

        if q["critical"] == "high":
            high_total += 1

        if user_ans == correct:
            score_brut += 1
            score_pondere += w
            if q["critical"] == "high":
                high_correct += 1
        else:
            u, c_ = answer_order(user_ans), answer_order(correct)
            if u < c_:
                under_est += 1
                etype = "sous-estimation"
            elif u > c_:
                over_est += 1
                etype = "sur-estimation"
            else:
                etype = "réponse vide"
            if q["critical"] == "high":
                critical_errors += 1
            erreurs_details.append(f"Q{qid}: répondu '{user_ans}' / attendu '{correct}' ({etype})")

    # Scores dimensionnels
    score_danger    = round(high_correct / high_total * 100, 1) if high_total else 0.0
    total_errors    = under_est + over_est
    score_precision = round((1 - under_est / max(total_errors, 1)) * 100, 1) if total_errors else 100.0
    taux            = round(score_brut / total * 100, 1)

    # Analyse IA des justifications
    ai_result = analyze_justifications_with_ai(st.session_state.justifs)
    score_justifs = ai_result.get("score_moyen", 0.0)
    synthese_justifs = ai_result.get("synthese", "")
    st.session_state.ai_analysis = ai_result

    # Aptitude
    if score_brut == total and critical_errors == 0:
        aptitude = "Apte — Score parfait"
    elif score_pondere >= round(MAX_WEIGHTED_SCORE * 0.90) and critical_errors == 0:
        aptitude = "Apte avec recommandation"
    else:
        aptitude = "Non apte — Formation requise"

    # Profil composite
    if score_danger >= 90 and score_justifs >= 2.5:
        profil = "Expert confirmé"
    elif score_danger >= 75 and score_justifs >= 1.5:
        profil = "Bon niveau opérationnel"
    elif score_danger >= 60:
        profil = "Niveau intermédiaire — vigilance sur les cas graves"
    elif under_est >= 4:
        profil = "Tendance à sous-estimer la gravité des désordres"
    elif over_est >= 4:
        profil = "Tendance à sur-estimer la gravité des désordres"
    else:
        profil = "Niveau insuffisant — formation prioritaire"

    result_data = {
        "nom": nom, "prenom": prenom, "email": email,
        "score_brut": score_brut, "total": total,
        "score_pondere": score_pondere, "score_pondere_max": MAX_WEIGHTED_SCORE,
        "taux_reussite": taux,
        "aptitude": aptitude, "profil": profil,
        "score_danger": score_danger,
        "score_precision": score_precision,
        "score_justifications": round(score_justifs, 2),
        "sous_estimation": under_est, "sur_estimation": over_est,
        "erreurs_critiques": critical_errors,
        "details_erreurs": " | ".join(erreurs_details) or "Aucune erreur.",
        "synthese_justifs": synthese_justifs,
        "ai_justifs": ai_result.get("justifications", {}),
    }

    # Recommandation IA
    result_data["recommandation"] = generate_ai_recommendation(result_data)
    return result_data


def generate_report(r):
    justifs_section = ""
    for qid, data in r.get("ai_justifs", {}).items():
        stars = "★" * data["score"] + "☆" * (3 - data["score"])
        justifs_section += f"  Q{qid} [{stars}] : {data['commentaire']}\n"
    if not justifs_section:
        justifs_section = "  Aucune justification analysée.\n"

    return f"""
RAPPORT INDIVIDUEL D'ÉVALUATION — TEST IQOA VIPP
==================================================
Employé : {r['prenom']} {r['nom']}
Email   : {r['email']}

1. RÉSULTATS GLOBAUX
--------------------
Score brut       : {r['score_brut']} / {r['total']}
Score pondéré    : {r['score_pondere']} / {r['score_pondere_max']}
Taux de réussite : {r['taux_reussite']} %
Aptitude         : {r['aptitude']}
Profil           : {r['profil']}

2. ANALYSE DES 3 DIMENSIONS
----------------------------
Détection du danger (questions Alerte) : {r['score_danger']} %
Précision du jugement                  : {r['score_precision']} %
Qualité des justifications             : {r['score_justifications']} / 3

Sous-estimations : {r['sous_estimation']}
Sur-estimations  : {r['sur_estimation']}
Erreurs critiques : {r['erreurs_critiques']}

3. ANALYSE IA DES JUSTIFICATIONS
----------------------------------
{justifs_section}
Synthèse : {r['synthese_justifs']}

4. RECOMMANDATION PERSONNALISÉE (générée par IA)
-------------------------------------------------
{r['recommandation']}

5. DÉTAIL DES ERREURS
----------------------
{r['details_erreurs']}
""".strip()


def send_report_email(to_email, subject, body):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and MAIL_FROM):
        raise RuntimeError("Configuration email incomplète.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg.set_content(body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as srv:
        srv.login(SMTP_USER, SMTP_PASSWORD)
        srv.send_message(msg)


# =========================================================
# PAGE HOME
# =========================================================
if st.session_state.page == "home":
    st.title("Questionnaire de validation des connaissances")
    st.subheader("Inspecteurs d'ouvrages d'art – Ponts VIPP")
    menu = st.sidebar.radio("Menu", ["Connexion", "Admin"])

    if menu == "Connexion":
        st.subheader("Connexion employé")
        nom    = st.text_input("Nom")
        prenom = st.text_input("Prénom")
        email  = st.text_input("Adresse e-mail")
        if st.button("Continuer"):
            if not nom or not prenom or not email:
                st.error("Tous les champs sont obligatoires.")
            elif "@" not in email:
                st.error("Adresse e-mail invalide.")
            else:
                st.session_state.nom    = nom
                st.session_state.prenom = prenom
                st.session_state.email  = email
                st.session_state.page   = "accueil"
                c.execute("INSERT INTO sessions_users(nom, prenom, email) VALUES (?, ?, ?)", (nom, prenom, email))
                conn.commit()
                st.rerun()

    elif menu == "Admin":
        st.subheader("Admin - Tableau des résultats")
        pwd = st.text_input("Mot de passe admin", type="password")
        if pwd == ADMIN_PASSWORD:
            df_s = pd.read_sql_query("SELECT nom, prenom, email, created_at FROM sessions_users ORDER BY created_at DESC", conn)
            df_r = pd.read_sql_query("""
                SELECT id, nom, prenom, email, score_brut, score_pondere, score_pondere_max,
                       taux_reussite, aptitude, profil, score_danger, score_precision,
                       score_justifications, erreurs_critiques, created_at, rapport
                FROM resultats ORDER BY created_at DESC
            """, conn)
            st.markdown("### Connexions")
            st.dataframe(df_s, use_container_width=True)
            st.markdown("### Résultats")
            st.dataframe(df_r.drop(columns=["rapport"]), use_container_width=True)
            if not df_r.empty:
                st.markdown("### Consulter un rapport")
                sel_id = st.selectbox(
                    "Choisir un résultat", df_r["id"].tolist(),
                    format_func=lambda x: (
                        f"ID {x} — {df_r[df_r['id']==x]['prenom'].iloc[0]} "
                        f"{df_r[df_r['id']==x]['nom'].iloc[0]} — "
                        f"{df_r[df_r['id']==x]['aptitude'].iloc[0]}"
                    ),
                )
                sel = df_r[df_r["id"] == sel_id].iloc[0]
                with st.expander("Rapport complet", expanded=True):
                    st.text(sel["rapport"])
                st.download_button(
                    "Télécharger", data=sel["rapport"].encode("utf-8"),
                    file_name=f"rapport_{sel['nom']}_{sel['prenom']}.txt", mime="text/plain",
                )


# =========================================================
# PAGE ACCUEIL UTILISATEUR
# =========================================================
elif st.session_state.page == "accueil":
    st.title(f"Bienvenue {st.session_state.prenom} {st.session_state.nom}")
    st.write(f"Email : {st.session_state.email}")
    st.markdown("### Légende IQOA")
    st.write("🟥 **Grave** — Voir à Alerte (3 à 3U) — Intervention immédiate requise")
    st.write("🟧 **Moyen** — (2 et 2E) — À surveiller")
    st.write("🟩 **Bénin** — (1) — Pas d'alerte nécessaire")
    st.info("ℹ️ Les questions critiques (Alerte) ont un poids plus important dans l'évaluation.")
    if st.button("Lancer le test"):
        st.session_state.page = "quiz"
        st.session_state.question = 1
        st.session_state.answers = {}
        st.session_state.justifs = {}
        st.session_state.result_saved = False
        st.session_state.mail_sent = False
        st.session_state.ai_analysis = None
        st.rerun()
    if st.button("Déconnexion"):
        st.session_state.page = "home"
        st.rerun()


# =========================================================
# PAGE QUIZ
# =========================================================
elif st.session_state.page == "quiz":
    qid = st.session_state.question
    q   = QUESTION_MAP[qid]

    st.title(f"Question {qid} / {len(QUESTIONS)}")
    st.caption(f"Thème : {SECTION_LABELS.get(q['theme'], q['theme'])}")
    st.progress(qid / len(QUESTIONS))

    if q["alerte"]:
        st.error("⚠️ Alerte — Intervention immédiate requise si mal classé")

    st.markdown(f"### {q['title']}")
    st.write(q["text"])

    img = QUESTION_IMAGES.get(qid)
    if img:
        if os.path.exists(img):
            st.image(img, use_column_width=True)
        else:
            st.info(f"Image attendue : {img}")

    options = ["Grave", "Moyen", "Bénin"]
    cur = st.session_state.answers.get(qid, "Grave")
    sel = st.radio(
        "Choisir la classe IQOA", options, index=options.index(cur),
        key=f"q_{qid}_radio",
        format_func=lambda x: {"Grave": "🟥 Grave", "Moyen": "🟧 Moyen", "Bénin": "🟩 Bénin"}[x],
    )
    st.session_state.answers[qid] = sel

    if q["requires_justification"]:
        justif = st.text_area(
            "Justification obligatoire — analysée par IA",
            value=st.session_state.justifs.get(qid, ""),
            key=f"q_{qid}_justif",
            placeholder="Expliquez brièvement votre diagnostic (cause, mécanisme, conséquence).",
        )
        st.session_state.justifs[qid] = justif

    col1, col2 = st.columns(2)
    if qid > 1:
        if col1.button("Précédent", key=f"prev_{qid}"):
            st.session_state.question -= 1
            st.rerun()
    if col2.button("Suivant" if qid < len(QUESTIONS) else "Terminer", key=f"next_{qid}"):
        if q["requires_justification"] and not st.session_state.justifs.get(qid, "").strip():
            st.error("La justification est obligatoire pour cette question.")
        else:
            if qid < len(QUESTIONS):
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

    with st.spinner("Analyse IA en cours..."):
        r = analyze_submission(st.session_state.nom, st.session_state.prenom, st.session_state.email)
    report_text = generate_report(r)

    # Aptitude
    if r["aptitude"] == "Apte — Score parfait":
        st.success("✅ Employé apte à sortir en terrain — Score parfait")
    elif r["aptitude"] == "Apte avec recommandation":
        st.warning("⚠️ Employé apte à sortir en terrain — Quelques points à consolider")
    else:
        st.error("❌ Employé non apte — Formation requise")

    st.markdown(f"**Profil :** {r['profil']}")

    # Métriques
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Score brut",      f"{r['score_brut']} / {r['total']}")
    col2.metric("Score pondéré",   f"{r['score_pondere']} / {r['score_pondere_max']}")
    col3.metric("Taux réussite",   f"{r['taux_reussite']} %")
    col4.metric("Erreurs critiques", r['erreurs_critiques'])

    col5, col6, col7 = st.columns(3)
    col5.metric("Détection danger",     f"{r['score_danger']} %")
    col6.metric("Précision jugement",   f"{r['score_precision']} %")
    col7.metric("Qualité justifications", f"{r['score_justifications']} / 3")

    # Analyse justifications IA
    if st.session_state.ai_analysis:
        st.markdown("### 📝 Analyse IA des justifications")
        for qid_str, data in st.session_state.ai_analysis.get("justifications", {}).items():
            stars = "★" * data["score"] + "☆" * (3 - data["score"])
            st.markdown(f"**Q{qid_str}** [{stars}] — {data['commentaire']}")
        if st.session_state.ai_analysis.get("synthese"):
            st.info(f"**Synthèse :** {st.session_state.ai_analysis['synthese']}")

    # Recommandation IA
    st.markdown("### 🤖 Recommandation personnalisée")
    st.write(r["recommandation"])

    with st.expander("Voir le rapport complet"):
        st.text(report_text)

    st.download_button(
        "Télécharger le rapport",
        data=report_text.encode("utf-8"),
        file_name=f"rapport_{st.session_state.nom}_{st.session_state.prenom}.txt",
        mime="text/plain",
    )

    if not st.session_state.result_saved:
        c.execute("""
            INSERT INTO resultats(nom, prenom, email, score_brut, score_pondere, score_pondere_max,
                taux_reussite, aptitude, profil, score_danger, score_precision,
                score_justifications, erreurs_critiques, sous_estimation, sur_estimation, rapport)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["nom"], r["prenom"], r["email"],
            r["score_brut"], r["score_pondere"], r["score_pondere_max"],
            r["taux_reussite"], r["aptitude"], r["profil"],
            r["score_danger"], r["score_precision"], r["score_justifications"],
            r["erreurs_critiques"], r["sous_estimation"], r["sur_estimation"],
            report_text,
        ))
        conn.commit()
        st.session_state.result_saved = True

    if not st.session_state.mail_sent:
        try:
            send_report_email(
                to_email=st.session_state.email,
                subject="Votre rapport d'évaluation VIPP — TEST IQOA",
                body=report_text,
            )
            st.success(f"Rapport envoyé à {st.session_state.email}.")
            st.session_state.mail_sent = True
        except Exception as e:
            st.warning(f"Rapport généré, mais envoi mail échoué : {e}")

    if st.button("Retour accueil"):
        st.session_state.page = "accueil"
        st.rerun()
