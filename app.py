import math
import os
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://api.football-data.org/v4"
DEFAULT_COMPETITIONS = {
    "Premier League (Angleterre)": "PL",
    "La Liga (Espagne)": "PD",
    "Bundesliga (Allemagne)": "BL1",
    "Serie A (Italie)": "SA",
    "Ligue 1 (France)": "FL1",
    "Ligue des champions": "CL",
}

st.set_page_config(page_title="Assistant de pronostics football", page_icon="⚽", layout="wide")
st.title("⚽ Assistant d'analyse et de pronostics football")
st.caption("Prototype statistique — utilise les données disponibles via football-data.org. Il ne place aucun pari.")

with st.sidebar:
    st.header("Configuration")
    api_token = st.text_input(
        "Jeton API football-data.org",
        value=os.getenv("FOOTBALL_DATA_TOKEN", ""),
        type="password",
        help="Créez un compte sur football-data.org et copiez votre jeton API. Ne le partagez pas."
    )
    competition_label = st.selectbox("Compétition", list(DEFAULT_COMPETITIONS.keys()))
    days_ahead = st.slider("Chercher les matchs des prochains jours", 1, 14, 7)
    st.caption("La disponibilité des compétitions et statistiques dépend de votre forfait API.")


def api_get(path, token, params=None):
    if not token:
        raise ValueError(
            "Saisissez votre jeton API dans le panneau de configuration."
        )

    response = requests.get(
        f"{API_BASE}{path}",
        headers={"X-Auth-Token": token},
        params=params or {},
        timeout=25,
    )

    if response.status_code == 401:
        raise RuntimeError(
            "Jeton API invalide ou non autorisé (HTTP 401)."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "Cette donnée ou compétition n'est pas incluse dans votre forfait (HTTP 403)."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "Limite de requêtes API atteinte (HTTP 429). Réessayez plus tard."
        )

    if not response.ok:
        raise RuntimeError(
            f"Erreur API HTTP {response.status_code} : {response.text}"
        )

    try:
        return response.json()
    except ValueError:
        raise RuntimeError(
            "L'API a renvoyé une réponse qui n'est pas au format JSON."
        )
        

def get_upcoming_matches(token, comp_code, days):
    today = date.today()
    data = api_get(
        f"/competitions/{comp_code}/matches",
        token,
        {
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=days)).isoformat(),
            "status": "SCHEDULED",
        },
    )
    matches = data.get("matches", [])
    rows = []
    for m in matches:
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        rows.append({
            "Date (UTC)": (m.get("utcDate") or "")[:16].replace("T", " "),
            "Domicile": home.get("name", "Inconnu"),
            "Extérieur": away.get("name", "Inconnu"),
            "match_id": m.get("id"),
            "home_id": home.get("id"),
            "away_id": away.get("id"),
            "competition": comp_code,
        })
    return pd.DataFrame(rows)

def get_team_recent_matches(token, team_id, comp_code, limit=10):
    data = api_get(
        f"/teams/{team_id}/matches",
        token,
        {"status": "FINISHED", "limit": limit},
    )
    matches = data.get("matches", [])

    # Garder uniquement les matchs de la compétition sélectionnée.
    return [
        match for match in matches
        if (match.get("competition") or {}).get("code") == comp_code
    ]

def team_goal_rates(matches, team_id, venue):
    # venue: "HOME" or "AWAY"; select matches played at that venue
    gf, ga = [], []
    for m in matches:
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        score = m.get("score", {}).get("fullTime") or {}
        hg, ag = score.get("home"), score.get("away")
        if hg is None or ag is None:
            continue
        if venue == "HOME" and home.get("id") == team_id:
            gf.append(float(hg)); ga.append(float(ag))
        elif venue == "AWAY" and away.get("id") == team_id:
            gf.append(float(ag)); ga.append(float(hg))
    return gf, ga

def overall_goal_rates(matches, team_id):
    gf, ga = [], []
    for m in matches:
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        score = m.get("score", {}).get("fullTime") or {}
        hg, ag = score.get("home"), score.get("away")
        if hg is None or ag is None:
            continue
        if home.get("id") == team_id:
            gf.append(float(hg)); ga.append(float(ag))
        elif away.get("id") == team_id:
            gf.append(float(ag)); ga.append(float(hg))
    return gf, ga

def mean_or(values, fallback):
    return sum(values) / len(values) if values else fallback

def poisson_pmf(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def estimate_probabilities(lambda_home, lambda_away, max_goals=8):
    p_home = p_draw = p_away = p_over25 = p_btts = 0.0
    score_probs = []
    for h in range(max_goals + 1):
        ph = poisson_pmf(h, lambda_home)
        for a in range(max_goals + 1):
            pa = poisson_pmf(a, lambda_away)
            p = ph * pa
            if h > a: p_home += p
            elif h == a: p_draw += p
            else: p_away += p
            if h + a >= 3: p_over25 += p
            if h > 0 and a > 0: p_btts += p
            score_probs.append((p, h, a))
    score_probs.sort(reverse=True)
    total = p_home + p_draw + p_away
    if total:
        p_home, p_draw, p_away = p_home/total, p_draw/total, p_away/total
    return {
        "1": p_home, "X": p_draw, "2": p_away,
        "Over 2,5": p_over25, "Les deux marquent": p_btts,
        "scores": [(h, a, p) for p, h, a in score_probs[:5]],
    }

def implied_probability(odds):
    try:
        odds = float(odds)
        return 1.0 / odds if odds > 1 else None
    except (ValueError, TypeError):
        return None

if not api_token:
    st.info("Pour lancer la recherche, ajoutez un jeton API football-data.org dans la barre latérale. Le jeton est utilisé uniquement par cette application.")
    st.markdown("""
    **Mise en route**
    1. Créez un compte sur [football-data.org](https://www.football-data.org/client/register).
    2. Récupérez votre jeton API.
    3. Collez-le dans le champ à gauche, puis cliquez sur **Rechercher les matchs**.
    """)
    st.stop()

if st.button("🔎 Rechercher les matchs", type="primary"):
    try:
        with st.spinner("Recherche des matchs..."):
            st.session_state["matches_df"] = get_upcoming_matches(
                api_token, DEFAULT_COMPETITIONS[competition_label], days_ahead
            )
    except Exception as e:
        st.error(f"Impossible de récupérer les matchs : {e}")

matches_df = st.session_state.get("matches_df")
if matches_df is not None:
    if matches_df.empty:
        st.warning("Aucun match programmé trouvé dans la période sélectionnée, ou données non disponibles.")
    else:
        st.success(f"{len(matches_df)} match(s) trouvé(s). Sélectionnez une rencontre pour l'analyse.")
        display = matches_df[["Date (UTC)", "Domicile", "Extérieur"]].copy()
        display["Rencontre"] = display["Domicile"] + " — " + display["Extérieur"]
        selected = st.selectbox("Rencontre", display["Rencontre"].tolist())
        row = matches_df.loc[(matches_df["Domicile"] + " — " + matches_df["Extérieur"]) == selected].iloc[0]

        st.subheader(selected)
        st.caption(f"Date de début prévue (UTC) : {row['Date (UTC)']}")

        st.markdown("### Cotes 1xBet (facultatif)")
        c1, cx, c2 = st.columns(3)
        with c1: odds1 = st.text_input("Cote victoire domicile", placeholder="ex. 2.10")
        with cx: oddsx = st.text_input("Cote match nul", placeholder="ex. 3.20")
        with c2: odds2 = st.text_input("Cote victoire extérieur", placeholder="ex. 3.50")

        if st.button("📊 Analyser ce match", type="primary"):
            try:
                with st.spinner("Récupération des derniers matchs et calcul des probabilités..."):
                    home_id, away_id = int(row["home_id"]), int(row["away_id"])
                    comp_code = row["competition"]
                    home_matches = get_team_recent_matches(api_token, home_id, comp_code, 10)
                    away_matches = get_team_recent_matches(api_token, away_id, comp_code, 10)

                    hgf, hga = overall_goal_rates(home_matches, home_id)
                    agf, aga = overall_goal_rates(away_matches, away_id)
                    # Blend venue-specific rates with overall rates when enough venue observations exist.
                    hgf_home, hga_home = team_goal_rates(home_matches, home_id, "HOME")
                    agf_away, aga_away = team_goal_rates(away_matches, away_id, "AWAY")
                    home_attack = 0.6 * mean_or(hgf_home, mean_or(hgf, 1.25)) + 0.4 * mean_or(hgf, 1.25)
                    home_defence = 0.6 * mean_or(hga_home, mean_or(hga, 1.25)) + 0.4 * mean_or(hga, 1.25)
                    away_attack = 0.6 * mean_or(agf_away, mean_or(agf, 1.0)) + 0.4 * mean_or(agf, 1.0)
                    away_defence = 0.6 * mean_or(aga_away, mean_or(aga, 1.0)) + 0.4 * mean_or(aga, 1.0)

                    # Transparent baseline; not a league-calibrated model.
                    lambda_home = max(0.15, min(4.0, (home_attack + away_defence) / 2))
                    lambda_away = max(0.15, min(4.0, (away_attack + home_defence) / 2))
                    probs = estimate_probabilities(lambda_home, lambda_away)

                st.subheader("Résultats du modèle")
                a, b = st.columns(2)
                a.metric("Buts attendus — domicile", f"{lambda_home:.2f}")
                b.metric("Buts attendus — extérieur", f"{lambda_away:.2f}")
                prob_df = pd.DataFrame({
                    "Issue": ["Victoire domicile (1)", "Nul (X)", "Victoire extérieur (2)", "Plus de 2,5 buts", "Les deux marquent"],
                    "Probabilité estimée": [probs["1"], probs["X"], probs["2"], probs["Over 2,5"], probs["Les deux marquent"]],
                })
                prob_df["Probabilité estimée"] = prob_df["Probabilité estimée"].map(lambda x: f"{x:.1%}")
                st.dataframe(prob_df, hide_index=True, use_container_width=True)

                st.markdown("**Scores exacts les plus probables (indicatifs)**")
                scores_df = pd.DataFrame([
                    {"Score": f"{h}–{a}", "Probabilité du score": f"{p:.1%}"}
                    for h, a, p in probs["scores"]
                ])
                st.dataframe(scores_df, hide_index=True, use_container_width=True)

                odds_inputs = [("1", odds1, probs["1"]), ("X", oddsx, probs["X"]), ("2", odds2, probs["2"])]
                odds_rows = []
                for outcome, odds, model_p in odds_inputs:
                    imp = implied_probability(odds)
                    if imp is not None:
                        odds_rows.append({
                            "Issue": outcome,
                            "Cote saisie": float(odds),
                            "Probabilité implicite brute": f"{imp:.1%}",
                            "Probabilité modèle": f"{model_p:.1%}",
                            "Écart modèle - implicite": f"{model_p-imp:+.1%}",
                        })
                if odds_rows:
                    st.markdown("**Comparaison aux cotes saisies**")
                    st.dataframe(pd.DataFrame(odds_rows), hide_index=True, use_container_width=True)
                    st.caption("Les probabilités implicites brutes incluent la marge du bookmaker et ne sont pas des probabilités justes.")
                st.info("Ce prototype utilise une approximation de Poisson et les derniers résultats accessibles. Il n'intègre pas encore les blessures, les compositions, la force des adversaires ni un ajustement calibré par championnat. N'utilisez pas ces résultats comme garantie de gain.")
            except Exception as e:
                st.error(f"Analyse impossible : {e}")
                st.caption("Vérifiez les permissions de votre jeton, la compétition choisie et la disponibilité des historiques pour ces équipes.")
