import os
import ssl
import smtplib
import sqlite3
from email.message import EmailMessage

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


SMTP_HOST = get_secret("SMTP_HOST")
SMTP_PORT = int(get_secret("SMTP_PORT", "465"))
SMTP_USER = get_secret("SMTP_USER")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD")
MAIL_FROM = get_secret("MAIL_FROM", SMTP_USER)
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin123")


# =========================================================
# BASE SQLITE
# =========================================================
conn = sqlite3.connect("inspecteurs.db", check_same_thread=False)
c = conn.cursor()

c.execute(
    """
    CREATE TABLE IF NOT EXISTS sessions_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT,
        prenom TEXT,
        email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
)

c.execute(
    """
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
    """
)
conn.commit()


# =========================================================
# QUESTIONS + CORRIGÉ
# =========================================================
QUESTIONS = [
    # --- POUTRES ---
    {
        "id": 1,
        "theme": "poutres",
        "title": "Question 1",
        "text": (
            "Fissure(s) régnant sur une hauteur pouvant atteindre et dépasser les deux tiers de la hauteur "
            "de la poutre, la poutre présentant par ailleurs une cambrure trop faible, voire nulle et même négative."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
        "has_image": True,
        "alerte": True,
    },
    {
        "id": 2,
        "theme": "poutres",
        "title": "Question 2",
        "text": (
            "Fissuration avec éclatement vertical d'une âme, de type IX, au droit des armatures transversales, "
            "due à un enrobage insuffisant de celles-ci, sans trace de rouille ni éclatement du béton."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 3,
        "theme": "poutres",
        "title": "Question 3",
        "text": (
            "Fissure(s) longitudinale(s) de type V, suivant le tracé d'un câble sur tout ou partie de sa longueur, "
            "le plus souvent en zone de mi-portée, sèche(s) et fine(s) le long d'un seul câble, "
            "d'ouverture inférieure à 0,3 mm."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 4,
        "theme": "poutres",
        "title": "Question 4",
        "text": (
            "Fracture horizontale du talon de type VII, pouvant régner sur plusieurs mètres dans la partie centrale "
            "de la travée, pouvant être accompagnée d'un rejet horizontal, due à une ou plusieurs des causes cumulées "
            "suivantes : cadres de couture de talons insuffisants, effet de poussée dû au gel de l'eau circulant dans "
            "des câbles mal injectés, poussée d'expansion par la rouille due à la corrosion d'armatures passives, "
            "des conduits et peut-être même des câbles de précontrainte."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
        "has_image": True,
        "alerte": True,
    },
    {
        "id": 5,
        "theme": "poutres",
        "title": "Question 5",
        "text": (
            "Décollements des cachetages des ancrages des câbles de précontrainte longitudinale, avec venue d'eau "
            "et/ou accompagnés d'efflorescences et/ou avec traces de rouille, à la limite ancrage ou éléments de câble "
            "visibles, en présence concomitante de fissures de type I (Q.1) et II (Q.6)."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
        "has_image": True,
        "alerte": True,
    },
    {
        "id": 6,
        "theme": "poutres",
        "title": "Question 6",
        "text": (
            "Fissure(s) oblique(s) de type II, proche(s) des zones sur appui, parfois combinée(s) avec des fissures "
            "de type I, due(s) à l'effet excessif combiné du moment fléchissant et de l'effort tranchant et/ou "
            "à une perte de précontrainte."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
        "has_image": True,
        "alerte": True,
    },
    {
        "id": 7,
        "theme": "poutres",
        "title": "Question 7",
        "text": (
            "Fissures à la jonction entre l'âme et le hourdis ou le talon, de type VIII, d'ouverture inférieure "
            "à 0,3 mm ou avec venue d'eau, dues au retrait gêné de l'âme par les coffrages laissés trop longtemps "
            "en place et/ou à une insuffisance d'armatures de couture entre d'une part le hourdis et d'autre part le talon."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 8,
        "theme": "poutres",
        "title": "Question 8",
        "text": (
            "Épaufrures du béton aux angles inférieurs d'une poutre, résultant de chocs lors des opérations de "
            "manutention à la construction et/ou aux chocs de véhicules hors gabarit circulant sur la voie franchie, "
            "sans mise à nu d'armature."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": False,
        "alerte": False,
    },
    {
        "id": 9,
        "theme": "poutres",
        "title": "Question 9",
        "text": (
            "Lacunes de béton en sous-face d'un talon de poutre à mi-travée, là où les armatures passives et actives "
            "sont les plus nombreuses, avec réduction des sections des armatures actives et/ou rupture de certaines "
            "d'entre elles, dues à un défaut de mise en œuvre du béton (vibrations insuffisantes, densité d'armatures "
            "importante) et/ou à une mauvaise formulation du béton."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
        "has_image": False,
        "alerte": True,
    },
    {
        "id": 10,
        "theme": "poutres",
        "title": "Question 10",
        "text": (
            "Fissure(s) localisée(s), épaufrures apparaissant lors des phases de manutention au droit des zones de "
            "levage, de type X, risquant de compromettre (fissuration importante, éclatements localisés importants) "
            "la résistance locale de la poutre."
        ),
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    # --- HOURDIS INTERMÉDIAIRES ---
    {
        "id": 11,
        "theme": "hourdis_intermediaires",
        "title": "Question 11",
        "text": (
            "Fissuration oblique en « arêtes de poisson » près des abouts des poutres, de type XII, due à "
            "l'insuffisance de couture du hourdis sous l'effet de la diffusion de précontrainte et de l'effort "
            "tranchant, fines et sèches."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 12,
        "theme": "hourdis_intermediaires",
        "title": "Question 12",
        "text": (
            "Fissures longitudinales de type XIV, dues à une insuffisance de résistance ou à des efforts appliqués "
            "plus importants que prévus et/ou à l'effet de câbles de précontrainte transversale (câbles mal excentrés, "
            "poussée au vide), nombreuses, avec venue d'eau, dans le cas d'un hourdis précontraint transversalement "
            "avec traces de corrosion."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
        "has_image": True,
        "alerte": True,
    },
    {
        "id": 13,
        "theme": "hourdis_intermediaires",
        "title": "Question 13",
        "text": (
            "Éclatement, décollement du béton de type XV, localisés, avec éclatements par plaques de certaines zones "
            "du hourdis, sans réduction notable des sections des armatures apparentes et/ou, pour les hourdis "
            "précontraints, avec mise à nu des armatures actives sans réduction notable de leurs sections."
        ),
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 14,
        "theme": "hourdis_intermediaires",
        "title": "Question 14",
        "text": (
            "Traces de circulation d'eau à travers le hourdis intermédiaire, liées à un défaut d'étanchéité en "
            "extrados, dues à l'absence totale ou partielle de chape d'étanchéité et/ou à des défauts de mise en "
            "œuvre de la chape, notamment aux raccordements sur les contre-bordures, les avaloirs, les joints de chaussée."
        ),
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
        "has_image": False,
        "alerte": False,
    },
    # --- HOURDIS EN ENCORBELLEMENT ---
    {
        "id": 15,
        "theme": "hourdis_encorbellement",
        "title": "Question 15",
        "text": (
            "Fissures de type XVII, transversales, réparties sur toute la longueur de l'encorbellement, dues au "
            "retrait gêné du béton de l'encorbellement coulé postérieurement à la poutre de rive, avec venue d'eau "
            "et/ou accompagnées d'efflorescences."
        ),
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 16,
        "theme": "hourdis_encorbellement",
        "title": "Question 16",
        "text": (
            "Fissuration oblique en « arêtes de poisson » près des abouts des poutres, de type XX, due à "
            "l'insuffisance d'armatures de couture du hourdis sous l'effet de la diffusion de précontrainte et "
            "de l'effort tranchant, avec venue d'eau et coulures de rouille."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 17,
        "theme": "hourdis_encorbellement",
        "title": "Question 17",
        "text": (
            "Décollements des cachetages des ancrages des câbles de précontrainte transversale, secs, dus à une "
            "mauvaise adhérence du matériau de cachetage et/ou à un retrait excessif lors de la mise en œuvre "
            "du cachetage."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": False,
        "alerte": False,
    },
    # --- ENTRETOISES ---
    {
        "id": 18,
        "theme": "entretoises",
        "title": "Question 18",
        "text": (
            "Fissurations obliques diverses de type XXII, verticales ou inclinées, sur entretoise en béton armé, "
            "dues à l'application d'efforts dissymétriques lors des phasages de mise en tension des poutres et du "
            "bétonnage du tablier et/ou à une insuffisante résistance aux effets de la flexion transversale, "
            "avec fissure(s) d'ouverture supérieure à 0,6 mm."
        ),
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    {
        "id": 19,
        "theme": "entretoises",
        "title": "Question 19",
        "text": (
            "Éclatement localisé de béton avec mise à nu d'armature(s) de type XXIII, dans l'angle inférieur "
            "d'une entretoise, dû à la poussée exercée par l'oxydation des armatures sur le béton d'enrobage, "
            "sans réduction notable des sections des armatures passives apparentes."
        ),
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
        "has_image": True,
        "alerte": False,
    },
    # --- DÉFAUTS DU MATÉRIAU BÉTON ---
    {
        "id": 20,
        "theme": "defauts_beton",
        "title": "Question 20",
        "text": (
            "Efflorescences et stalactites sèches résultant de l'entraînement de la chaux contenue dans le béton "
            "par les circulations d'eaux internes et de son dépôt sous forme de calcite en parement."
        ),
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
        "has_image": False,
        "alerte": False,
    },
]

QUESTION_MAP = {q["id"]: q for q in QUESTIONS}

# =========================================================
# IMAGES
# Questions avec image : 1,2,3,4,5,6,7,10,11,12,13,15,16,18,19
# Questions sans image : 8,9,14,17,20
# =========================================================
QUESTION_IMAGES = {
    qid: f"images/Image{qid}.png"
    for qid in [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 15, 16, 18, 19]
}

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
    strengths, weaknesses = [], []
    for theme, value in theme_percentages.items():
        if value >= 75:
            strengths.append(theme)
        elif value < 50:
            weaknesses.append(theme)
    return strengths, weaknesses


def analyze_justification_simple(text: str, keywords):
    text_low = (text or "").lower()
    found = [kw for kw in keywords if kw in text_low]
    if len(found) == 0:
        quality = "faible"
    elif len(found) <= 2:
        quality = "moyenne"
    else:
        quality = "bonne"
    return {"score": len(found), "concepts": ", ".join(found), "quality": quality}


def generate_recommendation(result_row):
    critical_errors = result_row.get("erreurs_critiques", 0)
    under = result_row.get("sous_estimation", 0)
    q1_quality = result_row.get("q1_qualite", "")
    q4_quality = result_row.get("q4_qualite", "")
    q6_quality = result_row.get("q6_qualite", "")

    if critical_errors >= 3:
        return "Une formation prioritaire sur l'identification des situations graves et des signaux d'alerte est recommandée."
    if under >= 4:
        return "Une sensibilisation au risque de sous-estimation des désordres structurels est recommandée."
    if q1_quality == "faible" or q4_quality == "faible" or q6_quality == "faible":
        return "Un renforcement du raisonnement technique écrit est recommandé sur les cas critiques."
    if result_row.get("taux_reussite", 0) >= 80:
        return "Le niveau est satisfaisant. Un maintien des acquis par retour d'expérience est recommandé."
    return "Une consolidation ciblée sur les thèmes les moins maîtrisés est recommandée."


def send_report_email(to_email: str, subject: str, body: str):
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and MAIL_FROM):
        raise RuntimeError("Configuration email incomplète.")
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

    # Analyse justifications des questions Alerte avec justification obligatoire
    q1_analysis = analyze_justification_simple(
        st.session_state.justifs.get(1, ""),
        ["fissure", "cambrure", "hauteur", "grave", "poutre", "affaissement"],
    )
    q4_analysis = analyze_justification_simple(
        st.session_state.justifs.get(4, ""),
        ["fracture", "talon", "gel", "câble", "rouille", "corrosion", "grave"],
    )
    q5_analysis = analyze_justification_simple(
        st.session_state.justifs.get(5, ""),
        ["cachetage", "ancrage", "eau", "rouille", "câble", "efflorescence", "grave"],
    )
    q6_analysis = analyze_justification_simple(
        st.session_state.justifs.get(6, ""),
        ["fissure", "oblique", "appui", "tranchant", "moment", "précontrainte", "grave"],
    )
    q9_analysis = analyze_justification_simple(
        st.session_state.justifs.get(9, ""),
        ["lacune", "talon", "armature", "rupture", "section", "grave"],
    )
    q12_analysis = analyze_justification_simple(
        st.session_state.justifs.get(12, ""),
        ["fissure", "longitudinale", "hourdis", "corrosion", "eau", "câble", "grave"],
    )

    theme_percentages = {
        theme: round((stats["correct"] / stats["total"]) * 100, 2) if stats["total"] > 0 else 0.0
        for theme, stats in theme_scores.items()
    }

    if score >= 16 and critical_errors <= 1:
        profil = "Bon niveau global"
    elif critical_errors >= 3:
        profil = "Faiblesse sur les situations graves"
    elif under_estimation >= 4:
        profil = "Tendance à sous-estimer la gravité"
    elif over_estimation >= 4:
        profil = "Tendance à sur-estimer la gravité"
    else:
        profil = "Niveau intermédiaire"

    return {
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
        "details_erreurs": " | ".join(erreurs_details),
        "q1_qualite": q1_analysis["quality"],
        "q4_qualite": q4_analysis["quality"],
        "q5_qualite": q5_analysis["quality"],
        "q6_qualite": q6_analysis["quality"],
        "q9_qualite": q9_analysis["quality"],
        "q12_qualite": q12_analysis["quality"],
        "theme_percentages": theme_percentages,
    }


def generate_report(result_row):
    strengths, weaknesses = get_strengths_and_weaknesses(result_row["theme_percentages"])
    strengths_text = ", ".join(strengths) if strengths else "Aucun point fort nettement dominant identifié."
    weaknesses_text = ", ".join(weaknesses) if weaknesses else "Aucune faiblesse majeure détectée."

    return f"""
RAPPORT INDIVIDUEL D'ÉVALUATION — TEST IQOA VIPP
==================================================

Employé : {result_row['prenom']} {result_row['nom']}
Email   : {result_row['email']}

1. Résultat global
------------------
Score          : {result_row['score']} / {result_row['total']}
Taux de réussite : {result_row['taux_reussite']} %
Profil         : {result_row['profil']}

2. Analyse du jugement
----------------------
Sous-estimations : {result_row['sous_estimation']}
Sur-estimations  : {result_row['sur_estimation']}
Erreurs critiques : {result_row['erreurs_critiques']}

3. Analyse des compétences par thème
--------------------------------------
Points forts  : {strengths_text}
Points faibles : {weaknesses_text}

4. Recommandation
-----------------
{generate_recommendation(result_row)}
""".strip()


# =========================================================
# PAGE HOME
# =========================================================
if st.session_state.page == "home":
    st.title("Questionnaire de validation des connaissances")
    st.subheader("Inspecteurs d'ouvrages d'art – Ponts VIPP")
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
            st.dataframe(df_results.drop(columns=["rapport"]), use_container_width=True)

            if not df_results.empty:
                st.markdown("### Consulter un rapport")
                selected_id = st.selectbox(
                    "Choisir un résultat",
                    df_results["id"].tolist(),
                    format_func=lambda x: (
                        f"ID {x} - {df_results[df_results['id'] == x]['prenom'].iloc[0]} "
                        f"{df_results[df_results['id'] == x]['nom'].iloc[0]} - "
                        f"Score {df_results[df_results['id'] == x]['score'].iloc[0]}/"
                        f"{df_results[df_results['id'] == x]['total'].iloc[0]}"
                    ),
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
    st.markdown("### Légende")
    st.write("🟥 **Grave** — Voir à Alerte (3 à 3U) — Intervention immédiate requise")
    st.write("🟧 **Moyen** — (2 et 2E) — À surveiller")
    st.write("🟩 **Bénin** — (1) — Pas d'alerte nécessaire")

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

    # Affichage section
    SECTION_LABELS = {
        "poutres": "Poutres",
        "hourdis_intermediaires": "Hourdis intermédiaires",
        "hourdis_encorbellement": "Hourdis en encorbellement",
        "entretoises": "Entretoises",
        "defauts_beton": "Défauts du matériau béton",
    }
    section_label = SECTION_LABELS.get(q["theme"], q["theme"])

    st.title(f"Question {qid} / {len(QUESTIONS)}")
    st.caption(f"Thème : {section_label}")
    st.progress(qid / len(QUESTIONS))

    if q["alerte"]:
        st.error("⚠️ Alerte — Intervention immédiate requise si mal classé")

    st.markdown(f"### {q['title']}")
    st.write(q["text"])

    # Image
    image_path = QUESTION_IMAGES.get(qid)
    if image_path:
        if os.path.exists(image_path):
            st.image(image_path, use_column_width=True)
        else:
            st.info(f"Image attendue : {image_path}")

    options = ["Grave", "Moyen", "Bénin"]
    current_answer = st.session_state.answers.get(qid, "Grave")

    selected = st.radio(
        "Choisir la classe IQOA",
        options,
        index=options.index(current_answer),
        key=f"q_{qid}_radio",
        format_func=lambda x: {"Grave": "🟥 Grave", "Moyen": "🟧 Moyen", "Bénin": "🟩 Bénin"}[x],
    )
    st.session_state.answers[qid] = selected

    if q["requires_justification"]:
        justif_default = st.session_state.justifs.get(qid, "")
        justif = st.text_area(
            "Justification obligatoire",
            value=justif_default,
            key=f"q_{qid}_justif",
            placeholder="Expliquez brièvement votre diagnostic.",
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

    result_row = analyze_submission(
        st.session_state.nom,
        st.session_state.prenom,
        st.session_state.email,
    )
    report_text = generate_report(result_row)

    st.subheader(f"Score : {result_row['score']} / {result_row['total']}")
    if result_row["score"] >= 16:
        st.success("✅ Employé apte à sortir en terrain")
    else:
        st.error("❌ Employé non apte – formation requise")

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
                subject="Votre rapport d'évaluation VIPP — TEST IQOA",
                body=report_text,
            )
            st.success(f"Le rapport a été envoyé à {st.session_state.email}.")
            st.session_state.mail_sent = True
        except Exception as e:
            st.warning(f"Rapport généré, mais l'envoi du mail a échoué : {e}")

    if st.button("Retour accueil"):
        st.session_state.page = "accueil"
        st.rerun()
