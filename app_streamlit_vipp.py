import os
import ssl
import json
import time
import smtplib
import sqlite3
import urllib.request
import urllib.error
from email.message import EmailMessage

import pandas as pd
import streamlit as st

# =========================================================
# CONFIG
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
GROQ_KEY       = get_secret("GROQ_API_KEY")

WEIGHTS = {"high": 3, "medium": 2, "low": 1}

# =========================================================
# BASE SQLITE
# =========================================================
conn = sqlite3.connect("inspecteurs.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS sessions_users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT, prenom TEXT, email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

c.execute("""CREATE TABLE IF NOT EXISTS resultats(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT, prenom TEXT, email TEXT,
    score_brut INTEGER, score_pondere INTEGER, score_pondere_max INTEGER,
    taux_reussite REAL, aptitude TEXT, profil TEXT,
    score_danger REAL, score_precision REAL, score_justifications REAL,
    erreurs_critiques INTEGER, sous_estimation INTEGER, sur_estimation INTEGER,
    rapport TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
conn.commit()

# =========================================================
# QUESTIONS
# =========================================================
QUESTIONS = [
    {"id": 1,  "theme": "poutres",               "title": "Question 1",
     "text": "Fissure(s) régnant sur une hauteur pouvant atteindre et dépasser les deux tiers de la hauteur de la poutre, la poutre présentant par ailleurs une cambrure trop faible, voire nulle et même négative.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},
    {"id": 2,  "theme": "poutres",               "title": "Question 2",
     "text": "Fissuration avec éclatement vertical d'une âme, de type IX, au droit des armatures transversales, due à un enrobage insuffisant de celles-ci, sans trace de rouille ni éclatement du béton.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 3,  "theme": "poutres",               "title": "Question 3",
     "text": "Fissure(s) longitudinale(s) de type V, suivant le tracé d'un câble sur tout ou partie de sa longueur, le plus souvent en zone de mi-portée, sèche(s) et fine(s) le long d'un seul câble, d'ouverture inférieure à 0,3 mm.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 4,  "theme": "poutres",               "title": "Question 4",
     "text": "Fracture horizontale du talon de type VII, pouvant régner sur plusieurs mètres dans la partie centrale de la travée, due à une ou plusieurs des causes cumulées suivantes : cadres de couture de talons insuffisants, gel, corrosion d'armatures passives et des câbles de précontrainte.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},
    {"id": 5,  "theme": "poutres",               "title": "Question 5",
     "text": "Décollements des cachetages des ancrages des câbles de précontrainte longitudinale, avec venue d'eau et/ou traces de rouille, éléments de câble visibles, en présence concomitante de fissures de type I (Q.1) et II (Q.6).",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},
    {"id": 6,  "theme": "poutres",               "title": "Question 6",
     "text": "Fissure(s) oblique(s) de type II, proche(s) des zones sur appui, parfois combinée(s) avec des fissures de type I, due(s) à l'effet excessif combiné du moment fléchissant et de l'effort tranchant et/ou à une perte de précontrainte.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},
    {"id": 7,  "theme": "poutres",               "title": "Question 7",
     "text": "Fissures à la jonction entre l'âme et le hourdis ou le talon, de type VIII, d'ouverture inférieure à 0,3 mm ou avec venue d'eau, dues au retrait gêné de l'âme par les coffrages laissés trop longtemps en place.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 8,  "theme": "poutres",               "title": "Question 8",
     "text": "Épaufrures du béton aux angles inférieurs d'une poutre, résultant de chocs lors des opérations de manutention ou aux chocs de véhicules hors gabarit, sans mise à nu d'armature.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": False, "alerte": False},
    {"id": 9,  "theme": "poutres",               "title": "Question 9",
     "text": "Lacunes de béton en sous-face d'un talon de poutre à mi-travée, avec réduction des sections des armatures actives et/ou rupture de certaines d'entre elles, dues à un défaut de mise en œuvre du béton.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": False, "alerte": True},
    {"id": 10, "theme": "poutres",               "title": "Question 10",
     "text": "Fissure(s) localisée(s), épaufrures apparaissant lors des phases de manutention au droit des zones de levage, de type X, risquant de compromettre la résistance locale de la poutre.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 11, "theme": "hourdis_intermediaires","title": "Question 11",
     "text": "Fissuration oblique en arêtes de poisson près des abouts des poutres, de type XII, due à l'insuffisance de couture du hourdis sous l'effet de la diffusion de précontrainte et de l'effort tranchant, fines et sèches.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 12, "theme": "hourdis_intermediaires","title": "Question 12",
     "text": "Fissures longitudinales de type XIV, nombreuses, avec venue d'eau et traces de corrosion, dans le cas d'un hourdis précontraint transversalement.",
     "correct": "Grave",  "critical": "high",   "requires_justification": True,  "has_image": True,  "alerte": True},
    {"id": 13, "theme": "hourdis_intermediaires","title": "Question 13",
     "text": "Éclatement, décollement du béton de type XV, localisés, sans réduction notable des sections des armatures apparentes et/ou avec mise à nu des armatures actives sans réduction notable de leurs sections.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 14, "theme": "hourdis_intermediaires","title": "Question 14",
     "text": "Traces de circulation d'eau à travers le hourdis intermédiaire, liées à un défaut d'étanchéité en extrados.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": False, "alerte": False},
    {"id": 15, "theme": "hourdis_encorbellement","title": "Question 15",
     "text": "Fissures de type XVII, transversales, réparties sur toute la longueur de l'encorbellement, avec venue d'eau et/ou accompagnées d'efflorescences.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 16, "theme": "hourdis_encorbellement","title": "Question 16",
     "text": "Fissuration oblique en arêtes de poisson près des abouts des poutres, de type XX, avec venue d'eau et coulures de rouille.",
     "correct": "Grave",  "critical": "high",   "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 17, "theme": "hourdis_encorbellement","title": "Question 17",
     "text": "Décollements des cachetages des ancrages des câbles de précontrainte transversale, secs, dus à une mauvaise adhérence du matériau de cachetage.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": False, "alerte": False},
    {"id": 18, "theme": "entretoises",           "title": "Question 18",
     "text": "Fissurations obliques diverses de type XXII sur entretoise en béton armé, avec fissure(s) d'ouverture supérieure à 0,6 mm.",
     "correct": "Grave",  "critical": "high",   "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 19, "theme": "entretoises",           "title": "Question 19",
     "text": "Éclatement localisé de béton avec mise à nu d'armature(s) de type XXIII dans l'angle inférieur d'une entretoise, sans réduction notable des sections des armatures passives apparentes.",
     "correct": "Moyen",  "critical": "medium", "requires_justification": False, "has_image": True,  "alerte": False},
    {"id": 20, "theme": "defauts_beton",         "title": "Question 20",
     "text": "Efflorescences et stalactites sèches résultant de l'entraînement de la chaux contenue dans le béton par les circulations d'eaux internes.",
     "correct": "Bénin",  "critical": "low",    "requires_justification": False, "has_image": False, "alerte": False},
]

QUESTION_MAP       = {q["id"]: q for q in QUESTIONS}
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


# =========================================================
# APPEL GROQ
# =========================================================
def call_groq(prompt: str, retries: int = 3) -> str:
    if not GROQ_KEY:
        return "⚠️ Clé API Groq non configurée."
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_KEY}"},
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(20 * (attempt + 1))
            else:
                return f"⚠️ Erreur Groq : HTTP {e.code}"
        except Exception as e:
            return f"⚠️ Erreur Groq : {e}"
    return "⚠️ Groq indisponible après plusieurs tentatives."


# =========================================================
# ANALYSE LOCALE (fallback sans IA)
# =========================================================
def fallback_analysis(justifs: dict, result_data: dict) -> dict:
    score_brut = result_data["score_brut"]
    total      = result_data["total"]
    danger     = result_data["score_danger"]
    under      = result_data["sous_estimation"]
    critical   = result_data["erreurs_critiques"]

    if score_brut == total:
        profil = "L'inspecteur maîtrise parfaitement la classification IQOA sur l'ensemble des thèmes."
    elif danger >= 80 and critical == 0:
        profil = "Bon niveau général avec une bonne détection des situations graves."
    elif critical >= 3:
        profil = "Des lacunes importantes sur les situations graves nécessitent une attention prioritaire."
    elif under >= 4:
        profil = "Tendance marquée à sous-estimer la gravité des désordres structurels."
    else:
        profil = f"Niveau intermédiaire avec {score_brut}/{total} bonnes réponses."

    theme_pct  = result_data.get("theme_pct", {})
    forts      = ", ".join([t for t, v in theme_pct.items() if v >= 75]) or "Aucun thème dominant."
    faibles    = ", ".join([t for t, v in theme_pct.items() if v < 50]) or "Aucune faiblesse majeure."

    if score_brut == total:
        reco = "Score parfait. Maintien des acquis par retour d'expérience recommandé."
    elif critical >= 3:
        reco = "Formation prioritaire sur la détection des désordres graves (Alerte). Révision du catalogue IQOA recommandée."
    elif under >= 4:
        reco = "Sensibilisation au risque de sous-estimation des désordres structurels. Étude de cas pratiques recommandée."
    else:
        reco = f"Formation ciblée recommandée sur les thèmes : {faibles}."

    keywords_map = {
        1:  ["fissure", "cambrure", "hauteur", "grave", "poutre"],
        4:  ["fracture", "talon", "gel", "câble", "rouille", "corrosion"],
        5:  ["cachetage", "ancrage", "eau", "rouille", "câble", "efflorescence"],
        6:  ["fissure", "oblique", "appui", "tranchant", "moment", "précontrainte"],
        9:  ["lacune", "talon", "armature", "rupture", "section"],
        12: ["fissure", "longitudinale", "hourdis", "corrosion", "eau", "câble"],
    }
    justif_results, scores = {}, []
    for qid, kws in keywords_map.items():
        txt   = (justifs.get(qid, "") or "").lower()
        found = [k for k in kws if k in txt]
        s     = min(3, len(found))
        scores.append(s)
        if s == 0:
            comment = "Justification absente ou hors sujet."
        elif s == 1:
            comment = f"Partielle — mentionne : {', '.join(found)}."
        elif s == 2:
            comment = f"Correcte — identifie : {', '.join(found)}."
        else:
            comment = f"Excellente — couvre les éléments clés : {', '.join(found)}."
        justif_results[str(qid)] = {"score": s, "commentaire": comment}

    return {
        "justifications": justif_results,
        "score_moyen":    round(sum(scores) / len(scores), 2) if scores else 0.0,
        "profil_global":  profil,
        "points_forts":   forts,
        "points_faibles": faibles,
        "recommandation": reco,
    }


# =========================================================
# ANALYSE IA (Groq) + fallback
# =========================================================
def analyze_and_recommend(justifs: dict, result_data: dict) -> dict:
    errors_block = ""
    for q in QUESTIONS:
        qid      = q["id"]
        user_ans = result_data["all_answers"].get(qid, "Grave")
        correct  = q["correct"]
        if user_ans != correct:
            justif = ""
            if q["requires_justification"]:
                justif = f" | Justif: {justifs.get(qid, '').strip() or '(aucune)'}"
            errors_block += f"Q{qid}[{q['theme']}]: répondu {user_ans}/attendu {correct}{justif}\n"

    justif_correct = ""
    for q in QUESTIONS:
        if q["requires_justification"]:
            qid = q["id"]
            if result_data["all_answers"].get(qid, "Grave") == q["correct"]:
                justif_correct += f"Q{qid}: {justifs.get(qid, '').strip() or '(aucune)'}\n"

    prompt = f"""Expert inspection ponts VIPP. Résultats inspecteur :
Score: {result_data['score_brut']}/{result_data['total']} ({result_data['taux_reussite']}%)
Score pondéré: {result_data['score_pondere']}/{result_data['score_pondere_max']}
Danger: {result_data['score_danger']}% | Précision: {result_data['score_precision']}%
Sous-estim: {result_data['sous_estimation']} | Sur-estim: {result_data['sur_estimation']} | Erreurs critiques: {result_data['erreurs_critiques']}

Erreurs:
{errors_block or 'Aucune.'}

Justifications questions critiques correctes:
{justif_correct or 'Aucune.'}

Réponds UNIQUEMENT en JSON sans markdown:
{{"justifications":{{"1":{{"score":0,"commentaire":"..."}},"4":{{"score":0,"commentaire":"..."}},"5":{{"score":0,"commentaire":"..."}},"6":{{"score":0,"commentaire":"..."}},"9":{{"score":0,"commentaire":"..."}},"12":{{"score":0,"commentaire":"..."}}}},"score_moyen":0.0,"profil_global":"...","points_forts":"...","points_faibles":"...","recommandation":"..."}}

Score justif: 0=absente,1=partielle,2=correcte,3=excellente. Recommandation: 3 phrases bienveillantes en français."""

    raw = call_groq(prompt)
    if raw.startswith("⚠️"):
        return fallback_analysis(justifs, result_data)

    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except Exception:
        return fallback_analysis(justifs, result_data)


# =========================================================
# ANALYSE SOUMISSION
# =========================================================
def analyze_submission(nom, prenom, email):
    score_brut, score_pondere = 0, 0
    under_est, over_est, critical_errors = 0, 0, 0
    high_correct, high_total = 0, 0
    erreurs_details = []
    theme_scores = {}

    for q in QUESTIONS:
        qid      = q["id"]
        user_ans = st.session_state.answers.get(qid, "Grave")
        correct  = q["correct"]
        w        = WEIGHTS[q["critical"]]
        theme    = q["theme"]

        if theme not in theme_scores:
            theme_scores[theme] = {"correct": 0, "total": 0}
        theme_scores[theme]["total"] += 1

        if q["critical"] == "high":
            high_total += 1

        if user_ans == correct:
            score_brut    += 1
            score_pondere += w
            theme_scores[theme]["correct"] += 1
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
            erreurs_details.append(f"Q{qid}: '{user_ans}' / attendu '{correct}' ({etype})")

    total         = len(QUESTIONS)
    taux          = round(score_brut / total * 100, 1)
    score_danger  = round(high_correct / high_total * 100, 1) if high_total else 0.0
    total_errors  = under_est + over_est
    score_prec    = round((1 - under_est / max(total_errors, 1)) * 100, 1) if total_errors else 100.0
    theme_pct     = {t: round(v["correct"] / v["total"] * 100, 1) for t, v in theme_scores.items()}

    if score_brut == total and critical_errors == 0:
        aptitude = "Apte — Score parfait"
    elif score_pondere >= round(MAX_WEIGHTED_SCORE * 0.90) and critical_errors == 0:
        aptitude = "Apte avec recommandation"
    else:
        aptitude = "Non apte — Formation requise"

    if score_danger >= 90 and score_brut >= 18:
        profil = "Expert confirmé"
    elif score_danger >= 75 and score_brut >= 15:
        profil = "Bon niveau opérationnel"
    elif score_danger >= 60:
        profil = "Niveau intermédiaire — vigilance sur les cas graves"
    elif under_est >= 4:
        profil = "Tendance à sous-estimer la gravité"
    elif over_est >= 4:
        profil = "Tendance à sur-estimer la gravité"
    else:
        profil = "Niveau insuffisant — formation prioritaire"

    ai_data = {
        "score_brut": score_brut, "total": total,
        "score_pondere": score_pondere, "score_pondere_max": MAX_WEIGHTED_SCORE,
        "taux_reussite": taux, "score_danger": score_danger,
        "score_precision": score_prec,
        "sous_estimation": under_est, "sur_estimation": over_est,
        "erreurs_critiques": critical_errors,
        "details_erreurs": " | ".join(erreurs_details) or "Aucune erreur.",
        "all_answers": st.session_state.answers,
        "theme_pct": theme_pct,
    }

    ai_result = analyze_and_recommend(st.session_state.justifs, ai_data)
    st.session_state.ai_analysis = ai_result

    return {
        "nom": nom, "prenom": prenom, "email": email,
        "score_brut": score_brut, "total": total,
        "score_pondere": score_pondere, "score_pondere_max": MAX_WEIGHTED_SCORE,
        "taux_reussite": taux, "aptitude": aptitude, "profil": profil,
        "score_danger": score_danger, "score_precision": score_prec,
        "score_justifications": round(ai_result.get("score_moyen", 0.0), 2),
        "sous_estimation": under_est, "sur_estimation": over_est,
        "erreurs_critiques": critical_errors,
        "details_erreurs": " | ".join(erreurs_details) or "Aucune erreur.",
        "profil_global":  ai_result.get("profil_global", ""),
        "points_forts":   ai_result.get("points_forts", ""),
        "points_faibles": ai_result.get("points_faibles", ""),
        "recommandation": ai_result.get("recommandation", ""),
        "ai_justifs":     ai_result.get("justifications", {}),
    }


# =========================================================
# RAPPORT TEXTE
# =========================================================
def generate_report(r):
    justifs_section = ""
    for qid, data in r.get("ai_justifs", {}).items():
        s     = data.get("score", 0)
        stars = "★" * s + "☆" * (3 - s)
        justifs_section += f"  Q{qid} [{stars}] : {data.get('commentaire', '')}\n"
    if not justifs_section:
        justifs_section = "  Aucune justification analysée.\n"

    return f"""RAPPORT INDIVIDUEL D'ÉVALUATION — TEST IQOA VIPP
==================================================
Employé : {r['prenom']} {r['nom']}
Email   : {r['email']}

1. RÉSULTATS GLOBAUX
--------------------
Score brut        : {r['score_brut']} / {r['total']}
Score pondéré     : {r['score_pondere']} / {r['score_pondere_max']}
Taux de réussite  : {r['taux_reussite']} %
Aptitude          : {r['aptitude']}
Profil            : {r['profil']}

2. ANALYSE DES 3 DIMENSIONS
----------------------------
Détection du danger   : {r['score_danger']} %
Précision du jugement : {r['score_precision']} %
Qualité justifications: {r['score_justifications']} / 3
Sous-estimations      : {r['sous_estimation']}
Sur-estimations       : {r['sur_estimation']}
Erreurs critiques     : {r['erreurs_critiques']}

3. ANALYSE DES JUSTIFICATIONS
------------------------------
{justifs_section}

4. PROFIL GLOBAL
----------------
{r.get('profil_global', 'Non disponible.')}

5. POINTS FORTS
---------------
{r.get('points_forts', 'Non disponible.')}

6. POINTS FAIBLES
-----------------
{r.get('points_faibles', 'Non disponible.')}

7. RECOMMANDATION PERSONNALISÉE
--------------------------------
{r.get('recommandation', 'Non disponible.')}

8. DÉTAIL DES ERREURS
----------------------
{r['details_erreurs']}""".strip()


# =========================================================
# EMAIL
# =========================================================
def send_report_email(to_email, subject, body):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and MAIL_FROM):
        raise RuntimeError("Configuration email incomplète.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = MAIL_FROM
    msg["To"]      = to_email
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
            df_r = pd.read_sql_query("""SELECT id, nom, prenom, email, score_brut, score_pondere,
                taux_reussite, aptitude, profil, score_danger, score_precision,
                score_justifications, erreurs_critiques, created_at, rapport
                FROM resultats ORDER BY created_at DESC""", conn)
            st.markdown("### Connexions")
            st.dataframe(df_s, use_container_width=True)
            st.markdown("### Résultats")
            st.dataframe(df_r.drop(columns=["rapport"]), use_container_width=True)
            if not df_r.empty:
                st.markdown("### Consulter un rapport")
                sel_id = st.selectbox("Choisir un résultat", df_r["id"].tolist(),
                    format_func=lambda x: (
                        f"ID {x} — {df_r[df_r['id']==x]['prenom'].iloc[0]} "
                        f"{df_r[df_r['id']==x]['nom'].iloc[0]} — "
                        f"{df_r[df_r['id']==x]['aptitude'].iloc[0]}"))
                sel = df_r[df_r["id"] == sel_id].iloc[0]
                with st.expander("Rapport complet", expanded=True):
                    st.text(sel["rapport"])
                st.download_button("Télécharger", data=sel["rapport"].encode("utf-8"),
                    file_name=f"rapport_{sel['nom']}_{sel['prenom']}.txt", mime="text/plain")


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
        st.session_state.page         = "quiz"
        st.session_state.question     = 1
        st.session_state.answers      = {}
        st.session_state.justifs      = {}
        st.session_state.result_saved = False
        st.session_state.mail_sent    = False
        st.session_state.ai_analysis  = None
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
    sel = st.radio("Choisir la classe IQOA", options, index=options.index(cur),
        key=f"q_{qid}_radio",
        format_func=lambda x: {"Grave": "🟥 Grave", "Moyen": "🟧 Moyen", "Bénin": "🟩 Bénin"}[x])
    st.session_state.answers[qid] = sel

    if q["requires_justification"]:
        justif = st.text_area("Justification obligatoire — analysée par IA",
            value=st.session_state.justifs.get(qid, ""),
            key=f"q_{qid}_justif",
            placeholder="Expliquez votre diagnostic (cause, mécanisme, conséquence).")
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

    with st.spinner("Analyse en cours..."):
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

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Score brut",       f"{r['score_brut']} / {r['total']}")
    col2.metric("Score pondéré",    f"{r['score_pondere']} / {r['score_pondere_max']}")
    col3.metric("Taux réussite",    f"{r['taux_reussite']} %")
    col4.metric("Erreurs critiques", r['erreurs_critiques'])

    col5, col6, col7 = st.columns(3)
    col5.metric("Détection danger",      f"{r['score_danger']} %")
    col6.metric("Précision jugement",    f"{r['score_precision']} %")
    col7.metric("Qualité justifications", f"{r['score_justifications']} / 3")

    # Justifications
    ai = st.session_state.ai_analysis or {}
    justifs_ai = ai.get("justifications", {})
    if justifs_ai:
        st.markdown("### 📝 Analyse des justifications")
        for qid_str, data in justifs_ai.items():
            s     = data.get("score", 0)
            stars = "★" * s + "☆" * (3 - s)
            st.markdown(f"**Q{qid_str}** [{stars}] — {data.get('commentaire', '')}")

    # Profil IA
    if ai.get("profil_global"):
        st.markdown("### 🧠 Profil global")
        st.write(ai["profil_global"])
    if ai.get("points_forts"):
        st.markdown("### ✅ Points forts")
        st.write(ai["points_forts"])
    if ai.get("points_faibles"):
        st.markdown("### ⚠️ Points faibles")
        st.write(ai["points_faibles"])
    if ai.get("recommandation"):
        st.markdown("### 🎯 Recommandation personnalisée")
        st.write(ai["recommandation"])

    with st.expander("Voir le rapport complet"):
        st.text(report_text)

    st.download_button("Télécharger le rapport", data=report_text.encode("utf-8"),
        file_name=f"rapport_{st.session_state.nom}_{st.session_state.prenom}.txt", mime="text/plain")

    if not st.session_state.result_saved:
        c.execute("""INSERT INTO resultats(nom, prenom, email, score_brut, score_pondere, score_pondere_max,
            taux_reussite, aptitude, profil, score_danger, score_precision,
            score_justifications, erreurs_critiques, sous_estimation, sur_estimation, rapport)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r["nom"], r["prenom"], r["email"],
             r["score_brut"], r["score_pondere"], r["score_pondere_max"],
             r["taux_reussite"], r["aptitude"], r["profil"],
             r["score_danger"], r["score_precision"], r["score_justifications"],
             r["erreurs_critiques"], r["sous_estimation"], r["sur_estimation"],
             report_text))
        conn.commit()
        st.session_state.result_saved = True

    if not st.session_state.mail_sent:
        try:
            send_report_email(st.session_state.email, "Votre rapport d'évaluation VIPP — TEST IQOA", report_text)
            st.success(f"Rapport envoyé à {st.session_state.email}.")
            st.session_state.mail_sent = True
        except Exception as e:
            st.warning(f"Rapport généré, mais envoi mail échoué : {e}")

    if st.button("Retour accueil"):
        st.session_state.page = "accueil"
        st.rerun()
