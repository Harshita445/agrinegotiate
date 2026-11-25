# AgriNegotiate

Fair prices on a bad signal. AgriNegotiate is a static web demo of delay-tolerant price negotiation for rural agricultural markets, where farmers and buyers keep negotiating even when connectivity drops in and out.

Live site: https://agrinegotiate.cv

## Files

- `index.html`: page structure
- `style.css`: styles
- `data.js`: market and scenario data
- `site.js`: interactive behaviour
- `CNAME`: custom domain for GitHub Pages

## Run locally

Open `index.html` in a browser, or serve the folder:

```
python -m http.server 8000
```

## Deployment

Hosted on GitHub Pages from the `main` branch (root), with the custom domain `agrinegotiate.cv`.

## Project code

The research code behind this demo lives in this repository as well: the negotiation simulator and learning agents in `agrinegotiate/`, experiment scripts in `experiments/`, tests in `tests/`, the paper draft in `paper/`, results in `results/`, and the extended project site in `site/`. See `PROJECT_README.md` for setup and the commands to train and evaluate the agents. Saved model checkpoints are not included; re-run the experiments to regenerate them.
