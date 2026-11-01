# Clasificación de bots

Esta página la reescribe la GitHub Action del torneo (`.github/workflows/tournament.yml`) al
fusionar en `main`, cada lunes o cuando se lanza a mano. Juegan todos los bots registrados
(los de MUS.ST, los de mus-cunef y los de `bots/`) todos contra todos, con repartos duplicados.

La clasificación usa el **Elo de Bradley-Terry** (media 1500; 200 puntos de diferencia ≈ 76 % de
victorias) y muestra el % de victorias con su margen al 95 %. También se ve en la web, en
**Campeonatos → Torneo de bots**.

Para jugarlo en local:

```bash
pip install -e ".[cunef]"
mus-torneo -n 6 --markdown docs/clasificacion.md
```
