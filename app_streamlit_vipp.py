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
# R = Grave, O = Moyen, V = Bénin
# Justifications : Q2, Q5, Q20
# =========================================================
QUESTIONS = [
    {
        "id": 1,
        "theme": "fleche_flexion",
        "title": "Question 1",
        "text": "Flèche longitudinale vers le bas en travée intéressant l'ensemble de la travée avec des fissure(s) verticale(s) de flexion, s'amorçant en partie basse de la poutre et remontant le plus souvent, située(s) dans la partie centrale de la travée.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 2,
        "theme": "affaissement_structurel",
        "title": "Question 2",
        "text": "Fissure(s) régnant sur une hauteur pouvant atteindre et dépasser les deux tiers de la hauteur de la poutre, la poutre présentant par ailleurs une cambrure trop faible, voire nulle et même négative : désordre grave indiquant un affaissement structurel anormal.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
    },
    {
        "id": 3,
        "theme": "nids_de_cailloux",
        "title": "Question 3",
        "text": "Nids de cailloux, dus à un défaut de mise en œuvre du béton (vibration insuffisante) et/ou à une mauvaise formulation (ségrégation), se présentant sous forme de zones superficielles peu étendues ou de défauts plus profonds et/ou étendus pouvant concerner une ou plusieurs poutres.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 4,
        "theme": "armatures_apparentes",
        "title": "Question 4",
        "text": "Armatures passives apparentes sans éclatement du béton, résultant d’un défaut de mise en œuvre (vibration insuffisante, densité d’armatures élevée).",
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
    },
    {
        "id": 5,
        "theme": "precontrainte_cables",
        "title": "Question 5",
        "text": "Fissure(s) suivant le tracé d’un ou de plusieurs câbles, régnant sur tout ou partie de leur longueur, le plus souvent en zone de mi-portée, accompagnées de venue d’eau, de traces de rouille, d’éclatements localisés ou étendus du béton, avec mise à nu d’armatures principales, réduction des sections des armatures actives et/ou rupture de certaines d’entre elles.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
    },
    {
        "id": 6,
        "theme": "ancrages_precontrainte",
        "title": "Question 6",
        "text": "Décollement des cachetages des ancrages des câbles de précontrainte longitudinale, avec venue d’eau, traces de rouille, et éléments de câble visibles, associé à la présence concomitante de fissures verticales de flexion et de fissures obliques proches des zones d’appui, révélateur d’une atteinte possible à l’efficacité des ancrages et à la sécurité structurelle.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 7,
        "theme": "eclatement_generalise",
        "title": "Question 7",
        "text": "Éclatement, d’écoulement du béton généralisés avec désenrobage des armatures sur des surfaces importantes et réduction de leurs sections, jusqu'à la rupture de certaines d'entre elles et/ou pour les hourdis précontraints, avec réduction notable des sections des armatures actives apparentes voire rupture de certaines d'entre elles.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 8,
        "theme": "cachetage_ancrages",
        "title": "Question 8",
        "text": "Décollement des cachetages des ancrages de précontrainte, avec eau, efflorescences associées à des fissures verticales et obliques proches des zones sur appui.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 9,
        "theme": "ecaillage",
        "title": "Question 9",
        "text": "Écaillage du béton se traduisant par un décollement du mortier de peau laissant apparaître les granulats, dû à des sollicitations mécaniques excessives, à l’action du gel, à l’agressivité du milieu (attaque chimique) et/ou à une mauvaise qualité du béton.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 10,
        "theme": "entretoise_precontrainte",
        "title": "Question 10",
        "text": "Lacunes de béton en sous-face ou en parement vertical d'une entretoise précontrainte avec réduction des sections des armatures actives et/ou rupture de certaines d'entre elles.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 11,
        "theme": "alcali_reaction",
        "title": "Question 11",
        "text": "Maillage régulier de fissures traduisant le développement d’une alcali-réaction, dans un environnement agressif, avec une intensité de fissuration importante et des répercussions notables sur le fonctionnement mécanique de l’ouvrage ; dans le cas des ouvrages en béton précontraint, ce maillage peut évoluer vers une fissuration orientée parallèlement aux efforts de compression.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": False,
    },
    {
        "id": 12,
        "theme": "cachetages_transversaux",
        "title": "Question 12",
        "text": "Décollements des cachetages des ancrages des câbles de précontrainte transversale sans venue d’eau.",
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
    },
    {
        "id": 13,
        "theme": "entretoise_fissures",
        "title": "Question 13",
        "text": "Fissurations obliques diverses de type XXII sur entretoise, verticales ou inclinées, cas d’une entretoise en béton armé : fissures plus nombreuses et/ou d’ouverture supérieure à 0,3 mm.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 14,
        "theme": "profil_longitudinal",
        "title": "Question 14",
        "text": "Rupture du profil longitudinal du tablier au droit d’un ou plusieurs appuis, résultant des déformations différées du béton (fluage) et/ou d’une mauvaise maîtrise des contreflèches.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 15,
        "theme": "lacunes_beton",
        "title": "Question 15",
        "text": "Les lacunes de béton correspondent à des défauts localisés de compacité se traduisant par des vides et une texture ouverte ; dans le cas 9.2, elles sont plus profondes, mettent à nu les armatures (passives et/ou de précontrainte) sans toutefois entraîner de réduction notable de leur section.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 16,
        "theme": "cachetage_sec",
        "title": "Question 16",
        "text": "Décollement des cachetages au droit des ancrages des câbles de précontrainte, sans trace d’humidité (état sec), dû à une mauvaise adhérence du matériau de cachetage et/ou à un retrait excessif lors de sa mise en œuvre.",
        "correct": "Bénin",
        "critical": "low",
        "requires_justification": False,
    },
    {
        "id": 17,
        "theme": "lacunes_superficielles",
        "title": "Question 17",
        "text": "Lacunes superficielles de béton en sous-face ou en parement vertical d’une entretoise précontrainte, sans mise à nu des armatures, dues à un défaut de mise en œuvre (vibration insuffisante, forte densité d’armatures) et/ou à une formulation inadaptée du béton.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 18,
        "theme": "epaufrures_poutre",
        "title": "Question 18",
        "text": "Épaufrures du béton aux angles inférieurs d’une poutre, résultant de chocs (manutention en phase de construction et/ou impacts de véhicules hors gabarit), avec déchirure des conduits de câbles de précontrainte sans atteinte des câbles eux-mêmes.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 19,
        "theme": "entretoise_eclatement",
        "title": "Question 19",
        "text": "Éclatement localisé du béton à l’angle inférieur d’une entretoise, avec mise à nu d’armatures passives présentant une réduction importante de section, dû à la poussée exercée par l’oxydation des aciers sur le béton d’enrobage.",
        "correct": "Moyen",
        "critical": "medium",
        "requires_justification": False,
    },
    {
        "id": 20,
        "theme": "desagregation",
        "title": "Question 20",
        "text": "Désagrégation du béton se traduisant par une destruction en profondeur, étendue, due à une mauvaise qualité du béton et/ou à l'action du gel et/ou à l'agressivité du milieu environnant (attaque chimique), compromettant la durabilité et la capacité portante de l’élément.",
        "correct": "Grave",
        "critical": "high",
        "requires_justification": True,
    },
]

QUESTION_MAP = {q["id"]: q for q in QUESTIONS}

# =========================================================
# IMAGES
# Mets tes images PNG dans le dossier images/ à la racine du projet.
# Les fichiers extraits du document incluent notamment image2.png, image3.png,
# image8.png, image9.png, image10.png, image11.png. Les .emf sont à convertir en PNG.
# =========================================================
QUESTION_IMAGES = {
    1: "images/Image1.png",
    2: "images/Image2.png",
    3: "images/Image3.png",
    4: "images/Image4.png",
    5: "images/Image5.png",
    6: "images/Image6.png",
    7: "images/Image7.png",
    8: "images/Image8.png",
    9: "images/Image9.png",
    10: "images/Image10.png",
    11: "images/Image11.png",
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
    strengths = []
    weaknesses = []
    for theme, value in theme_percentages.items():
        if value >= 75:
            strengths.append(theme)
        elif value < 50:
            weaknesses.append(theme)
    return strengths, weaknesses


def analyze_justification_simple(text: str, keywords: list[str]):
    text_low = (text or "").lower()
    found = [kw for kw in keywords if kw in text_low]
    if len(found) == 0:
        quality = "faible"
    elif len(found) <= 2:
        quality = "moyenne"
    else:
        quality = "bonne"
    return {
        "score": len(found),
        "concepts": ", ".join(found),
        "quality": quality,
    }


def generate_recommendation(result_row):
    critical_errors = result_row.get("erreurs_critiques", 0)
    under = result_row.get("sous_estimation", 0)
    q2_quality = result_row.get("q2_qualite", "")
    q5_quality = result_row.get("q5_qualite", "")
    q20_quality = result_row.get("q20_qualite", "")

    if critical_errors >= 3:
        return "Une formation prioritaire sur l'identification des situations graves et des signaux d’alerte est recommandée."
    if under >= 4:
        return "Une sensibilisation au risque de sous-estimation des désordres structurels est recommandée."
    if q2_quality == "faible" or q5_quality == "faible" or q20_quality == "faible":
        return "Un renforcement du raisonnement technique écrit est recommandé sur les cas critiques."
    if result_row.get("taux_reussite", 0) >= 80:
        return "Le niveau est satisfaisant. Un maintien des acquis par retour d’expérience est recommandé."
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

    q2_analysis = analyze_justification_simple(
        st.session_state.justifs.get(2, ""),
        ["fissure", "cambrure", "affaissement", "grave", "structure", "poutre"],
    )
    q5_analysis = analyze_justification_simple(
        st.session_state.justifs.get(5, ""),
        ["cable", "precontrainte", "rouille", "eau", "eclatement", "grave"],
    )
    q20_analysis = analyze_justification_simple(
        st.session_state.justifs.get(20, ""),
        ["desagregation", "beton", "gel", "attaque chimique", "grave", "portante"],
    )

    theme_percentages = {}
    for theme, stats in theme_scores.items():
        pct = round((stats["correct"] / stats["total"]) * 100, 2) if stats["total"] > 0 else 0.0
        theme_percentages[theme] = pct

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
        "details_erreurs": " | ".join(erreurs_details),
        "q2_nlp_score": q2_analysis["score"],
        "q2_concepts": q2_analysis["concepts"],
        "q2_qualite": q2_analysis["quality"],
        "q5_nlp_score": q5_analysis["score"],
        "q5_concepts": q5_analysis["concepts"],
        "q5_qualite": q5_analysis["quality"],
        "q20_nlp_score": q20_analysis["score"],
        "q20_concepts": q20_analysis["concepts"],
        "q20_qualite": q20_analysis["quality"],
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

    st.title(f"Question {qid} / {len(QUESTIONS)}")
    st.progress(qid / len(QUESTIONS))
    st.markdown(f"### {q['title']}")
    st.write(q["text"])

    image_path = QUESTION_IMAGES.get(qid)
    if image_path and os.path.exists(image_path):
        st.image(image_path, use_container_width=True)
    elif image_path:
        st.info(f"Image attendue : {image_path}")

    options = ["Grave", "Moyen", "Bénin"]
    current_answer = st.session_state.answers.get(qid, "Grave")

    selected = st.radio(
        "Choisir la gravité",
        options,
        index=options.index(current_answer),
        key=f"q_{qid}_radio",
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
