# ft_transcendence

Plateforme web de **Pong** multijoueur avec tournois, authentification (OAuth 42, JWT, 2FA), interface multilingue et architecture **microservices** orchestrée par Docker.

Projet réalisé dans le cadre du cursus **42** (sujet *ft_transcendence*).

## À propos

**ft_transcendence** permet de :

- **S’authentifier** via l’API OAuth de l’intranet 42, avec sessions sécurisées (JWT) et **2FA** (TOTP / QR code).
- **Jouer au Pong** en temps réel : logique de jeu **côté serveur**, clients connectés en WebSocket (y compris parties à distance).
- **Organiser des tournois** : création, file d’attente et résultats persistés côté matchmaker / base de données.
- **Consulter profils, classements et statistiques** depuis le tableau de bord Django.
- **Changer de langue** (anglais, français, allemand) dans l’interface.

## Fonctionnalités (modules sujet)

| Domaine | Implémentation |
|--------|----------------|
| **Web** | Backend **Django** 5, front statique / SPA, **PostgreSQL** |
| **Comptes** | Utilisateurs personnalisés, OAuth 42, profils, tournois liés aux comptes |
| **Gameplay** | Pong **server-side**, API et WebSocket dédiés au service jeu |
| **Sécurité** | **JWT** (cookies session), **2FA** (django-otp), chiffrement (Fernet / `cryptography`) |
| **DevOps** | **Docker Compose** : nginx (TLS), web, PostgreSQL, RabbitMQ, matchmaker, game |
| **Accessibilité** | **i18n** Django (en / fr / de) |
| **Stats** | Tableaux de bord utilisateur et parties |

## Architecture

Les services communiquent notamment via **RabbitMQ** (RPC JSON) pour créer des parties et remonter les résultats.

```text
Navigateur ──HTTPS──► nginx:4243 ──► Django (web:8000)
                         │
         WebSocket jeu ──┼──► game (plage de ports PORT_RANGE)
                         │
              RabbitMQ ◄─┴──► matchmaker · game (RPC)
                         │
                    PostgreSQL
```

- **nginx** : terminaison TLS (certificat auto-signé généré au premier démarrage si absent), reverse proxy vers Django, fichiers statiques.
- **web** : application Django (`web/`), ORM, vues, internationalisation.
- **matchmaker** : appariements, tournois, WebSocket vers les clients, appels RPC vers le service jeu.
- **game** : processus Python qui lance des **GameServer** WebSocket sur une plage de ports, valide les JWT, transmet les scores au broker.
- **postgres** : données utilisateurs, parties, tournois.
- **rabbitmq** : bus de messages pour le RPC (*tinyrpc* / *pika*).

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) et [Docker Compose](https://docs.docker.com/compose/) (plugin `docker compose` ou binaire `docker-compose`).
- Un **UID / secret OAuth** pour l’application enregistrée sur l’intranet 42 (redirect URI en HTTPS, voir ci-dessous).

## Installation

```bash
# 1. Cloner le dépôt
git clone <url-de-votre-depot>.git
cd ft_transcendence

# 2. Créer un fichier .env à la racine (non versionné)
#    Renseigner toutes les variables attendues par docker-compose.yml
#    (voir section Configuration).

# 3. Lancer la stack
make          # équivalent à : docker-compose up -d
# ou, pour reconstruire les images :
make re
```

L’application est ensuite exposée selon `docker-compose.yml` :

- **HTTP → HTTPS** : port `8001` (redirection vers HTTPS).
- **HTTPS (site + API)** : port **`4243`** (certificat dans le volume `certificates`).

Ouvrez `https://<PUBLIC_HOST>:4243` (acceptez l’avertissement du navigateur si le certificat est auto-signé).

### Makefile

| Cible | Effet |
|-------|--------|
| `make` / `make all` | `docker-compose up -d` |
| `make clean` | Arrêt des conteneurs |
| `make fclean` | Arrêt + suppression images et volumes |
| `make re` | Rebuild puis `up -d` |

## Configuration (`.env`)

Créez un fichier **`.env`** à la racine du dépôt. Variables typiques (noms alignés sur `docker-compose.yml` et le code) :

| Variable | Rôle |
|----------|------|
| `PUBLIC_HOST` | Nom d’hôte attendu par nginx / Django (`ALLOWED_HOSTS`, certificat TLS). |
| `PUBLIC_PORT` | Port public HTTPS (souvent `4243`) pour l’URL de callback OAuth dans les templates. |
| `POSTGRES_HOST` | En Compose : `postgres`. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Identifiants base de données. |
| `OAUTH2_UID`, `OAUTH2_SECRET` | Identifiants application API 42. |
| `JWT_SECRET` | Secret de signature des JWT (partagé avec matchmaker / jeu). |
| `ENCRYPTION_KEY` | Utilisé comme `SECRET_KEY` Django et pour Fernet : doit être une clé **Fernet** valide (44 caractères Base64 URL-safe) si vous activez les chemins qui chiffrent des données. |
| `RPC_HOST` | Hôte RabbitMQ depuis les conteneurs : `rabbitmq`. |
| `MATCHMAKER_SERVICE` | Nom de file RPC du matchmaker (cohérent avec le client Django, ex. `matchmaker_service_queue`). |
| `GAME_HOST` | Hôte **vu par le navigateur** pour se connecter aux serveurs de jeu (souvent `localhost` ou l’IP de la machine hôte selon votre réseau). |
| `PORT_RANGE` | Plage exposée pour les WebSocket jeu, format `début-fin` (ex. `9000-9010`). Doit correspondre au mapping `ports` du service `game`. |
| `MAX_TOURNAMENTS` | Limite de tournois simultanés côté matchmaker. |
| `MIN_TOURNAMENT_PLAYERS`, `MAX_TOURNAMENT_PLAYERS` | Bornes affichées / utilisées pour la création de tournois. |

**OAuth 42** : l’URL de redirection doit correspondre à
`https://<PUBLIC_HOST>:<PUBLIC_PORT>/auth`
(telle qu’utilisée dans `web/frontapp/views.py` et les templates de login).

## Utilisation rapide

1. Remplir `.env` et lancer `make`.
2. Accéder au site en HTTPS sur le port configuré (ex. `4243`).
3. Se connecter avec le bouton **Login** (flux 42), activer la **2FA** depuis le profil si besoin.
4. Lancer une partie classique ou rejoindre / créer un **tournoi** depuis l’interface.

## Structure du projet

```text
ft_transcendence/
├── docker-compose.yml      # Orchestration des services
├── Makefile
├── docker/
│   └── nginx.template      # Modèle de config nginx (TLS + proxy)
├── web/                    # Backend Django + templates + static
│   ├── frontapp/           # Modèles, vues, RPC client matchmaker, i18n
│   ├── frontend/           # settings, urls, locale
│   └── static/, templates/
├── matchmaker/             # Service d’appariement (async, WebSocket, RPC)
├── game/
│   ├── server/             # Boucle de jeu WebSocket, protocole
│   ├── service/            # Orchestration des instances de jeu + RPC
│   └── tools/              # Scripts utilitaires (JWT, tests, etc.)
└── requirements.txt        # Dépendances Python racine (si utilisé)
```

## Technologies principales

- **Python 3.12** (images officielles) / **Alpine** pour le service jeu.
- **Django 5**, **PostgreSQL**, **nginx**.
- **RabbitMQ**, **pika**, **tinyrpc** (RPC).
- **websockets**, **PyJWT**, **django-allauth**, **django-otp**, **Pillow**, **cryptography**.

Pour le détail des versions Python, voir `web/requirements.txt`, `matchmaker/requirements.txt` et `game/requirements.txt`.

## Dépannage

| Problème | Piste |
|----------|--------|
| Conteneur `web` unhealthy | Vérifier migrations / `collectstatic` et la création du fichier `/tmp/ready` dans `web/container.sh`. |
| Erreur de connexion à la base | `POSTGRES_HOST=postgres`, identifiants identiques à ceux du service `postgres`. |
| OAuth 42 refusé | Redirect URI exacte, `PUBLIC_HOST` / `PUBLIC_PORT` cohérents avec l’URL réelle. |
| WebSocket jeu impossible | `GAME_HOST` et ports exposés (`PORT_RANGE`) accessibles depuis le navigateur (pare-feu, Docker Desktop). |
| Certificat non fiable | Normal en dev : certificat généré par OpenSSL au premier run (`/certificates` dans le conteneur web). |

## Auteurs

Projet **42** — dépôt **ft_transcendence**
Réalisé par **raniaXdaoudi**, **tbesson** et **dkermia**.
