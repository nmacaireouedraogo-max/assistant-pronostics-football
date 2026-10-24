# Assistant de pronostics football — prototype

## Fonctionnalités
- Recherche les rencontres à venir via l'API football-data.org.
- Récupère les derniers matchs terminés des équipes lorsque l'abonnement autorise ces données.
- Calcule une estimation de buts attendus et des probabilités 1/X/2, plus de 2,5 buts et les deux équipes marquent avec un modèle de Poisson simplifié.
- Permet de saisir manuellement les cotes 1xBet pour comparer leurs probabilités implicites aux estimations du modèle.
- Ne se connecte pas au compte 1xBet et ne place aucun pari.

## Installation sous Windows
1. Installez Python 3.11 ou plus récent depuis https://www.python.org/downloads/
2. Décompressez le dossier.
3. Ouvrez l'invite de commandes dans ce dossier.
4. Exécutez :
   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   streamlit run app.py
   ```
5. Créez un compte sur https://www.football-data.org/client/register et obtenez un jeton API.
6. Collez le jeton dans la barre latérale de l'application.

## Installation sous Linux/macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Limites
- La couverture des compétitions et des historiques dépend du forfait football-data.org.
- Les cotes de 1xBet sont saisies manuellement dans cette première version : aucune API officielle 1xBet n'est supposée disponible.
- Le modèle est une base pédagogique, pas un modèle validé pour gagner de l'argent. Il faut le tester sur des données hors échantillon et mesurer sa calibration avant tout usage réel.
- Ne partagez jamais votre jeton API. L'application ne le sauvegarde pas volontairement dans un fichier.
