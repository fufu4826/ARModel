# System Design

## Overview

ARModel is a Flask web application. Flask serves HTML pages and JSON APIs, `models.json` and `projects.json` store model/project metadata, and `static/model` plus `static/pic` store 3D assets and thumbnails.

## Architecture Diagram

```text
User Browser
   |
   v
Flask App
   |
   +--> templates/*.html
   +--> static/model/*.glb
   +--> static/pic/*
   +--> models.json
   +--> projects.json
```

## Main Components

- Flask backend for routing, admin sessions, CRUD actions, and APIs.
- HTML templates for home, project, model detail, login, and admin screens.
- Google model-viewer frontend for 3D viewing and AR launch.
- JSON metadata files for projects and models.
- Static asset storage for `.glb` files, thumbnails, and logos.

## AR Viewer Flow

```text
User opens model page
   |
Flask loads model metadata
   |
Template renders model-viewer
   |
Browser loads .glb
   |
User rotates / zooms / opens AR
```

## Deployment Flow

```text
Developer
   |
GitHub
   |
Vercel
   |
Public Website
```

## Future Improvements

- Admin upload model
- Database migration
- Search and categories
- Metadata editor
- Cloud object storage
- User analytics
- Multi-language support
