# Backend Development Guidelines

> Best practices for backend development in this project (FastAPI + Redis + SQLite).

---

## Overview

This directory contains guidelines for backend development. The backend is a FastAPI application with Redis for job queues and SQLite for user data.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Auth Pattern](./auth-pattern.md) | OAuth + JWT + user isolation | Active |

---

## Architecture Summary

- **Framework**: FastAPI (async)
- **Job Queue**: Redis + RQ (python-rq)
- **User Database**: SQLite (SQLAlchemy ORM)
- **Auth**: LinuxDo OAuth 2.0 + JWT (httponly cookies)
- **Config**: Pydantic Settings from `.env`

---

**Language**: All documentation should be written in **English**.
