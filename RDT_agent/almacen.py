"""Persistencia del estado de la app (operadores + configuración del rol).

Dos backends, se elige solo:

* **LocalStore** — archivos JSON en disco (uso local).
* **GitHubStore** — guarda los JSON en una rama del repo vía la API de GitHub
  (uso en Streamlit Cloud, donde el disco es efímero). Escribe en una rama de
  datos separada (por defecto ``app-data``) para no disparar un redeploy cada
  vez que se guarda.

Sin dependencias externas: sólo `urllib` de la stdlib.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request

_API = "https://api.github.com"
_TIMEOUT = 20


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
#  Local                                                                       #
# --------------------------------------------------------------------------- #

class LocalStore:
    kind = "local"

    def __init__(self, directory: str):
        self.dir = directory
        self.last_error: str | None = None

    def _p(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def load(self, name: str):
        try:
            with open(self._p(name), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:  # JSON corrupto, etc.
            self.last_error = f"{name}: {e}"
            return None

    def save(self, name: str, obj) -> None:
        try:
            with open(self._p(name), "w", encoding="utf-8") as f:
                f.write(_dump(obj))
            self.last_error = None
        except Exception as e:
            self.last_error = f"{name}: {e}"

    def describe(self) -> str:
        return f"local — {self.dir}"


# --------------------------------------------------------------------------- #
#  GitHub                                                                      #
# --------------------------------------------------------------------------- #

class GitHubStore:
    kind = "github"

    def __init__(self, token: str, repo: str, branch: str = "app-data",
                 prefix: str = ""):
        self.token = token
        self.repo = repo.strip().strip("/")
        self.branch = branch
        self.prefix = prefix.strip("/")
        self.last_error: str | None = None
        self._sha: dict[str, str] = {}
        self._hash: dict[str, str] = {}
        self._branch_ok = False

    # --- HTTP ---------------------------------------------------------------
    def _req(self, method: str, url: str, body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "rdt-agent-turnos")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                payload = r.read()
                return r.status, (json.loads(payload) if payload else None)
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                return e.code, json.loads(payload) if payload else None
            except Exception:
                return e.code, {"message": payload.decode("utf-8", "replace")}

    def _path(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    # --- rama de datos ----------------------------------------------------
    def _ensure_branch(self) -> None:
        if self._branch_ok:
            return
        code, _ = self._req("GET", f"{_API}/repos/{self.repo}/branches/{self.branch}")
        if code == 200:
            self._branch_ok = True
            return
        code, info = self._req("GET", f"{_API}/repos/{self.repo}")
        default = (info or {}).get("default_branch", "main")
        code, ref = self._req(
            "GET", f"{_API}/repos/{self.repo}/git/ref/heads/{default}")
        if code != 200:
            raise RuntimeError(f"no pude leer la rama '{default}': {ref}")
        sha = ref["object"]["sha"]
        code, resp = self._req(
            "POST", f"{_API}/repos/{self.repo}/git/refs",
            {"ref": f"refs/heads/{self.branch}", "sha": sha})
        if code not in (201, 422):  # 422 = ya existe (carrera)
            raise RuntimeError(f"no pude crear la rama '{self.branch}': {resp}")
        self._branch_ok = True

    def _refresh_sha(self, name: str) -> None:
        url = (f"{_API}/repos/{self.repo}/contents/{self._path(name)}"
               f"?ref={self.branch}")
        code, resp = self._req("GET", url)
        if code == 200:
            self._sha[name] = resp["sha"]

    # --- API pública ----------------------------------------------------
    def load(self, name: str):
        url = (f"{_API}/repos/{self.repo}/contents/{self._path(name)}"
               f"?ref={self.branch}")
        try:
            code, resp = self._req("GET", url)
            if code == 200 and resp and "content" in resp:
                self._sha[name] = resp["sha"]
                raw = base64.b64decode(resp["content"]).decode("utf-8")
                self._hash[name] = _hash(raw)
                return json.loads(raw)
            if code not in (200, 404):
                self.last_error = f"load {name}: {code} {resp}"
        except Exception as e:
            self.last_error = f"load {name}: {e}"
        return None

    def save(self, name: str, obj) -> None:
        raw = _dump(obj)
        h = _hash(raw)
        if self._hash.get(name) == h:
            return  # sin cambios, no se hace commit
        try:
            self._ensure_branch()
            url = f"{_API}/repos/{self.repo}/contents/{self._path(name)}"
            body = {
                "message": f"app: actualizar {name}",
                "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
                "branch": self.branch,
            }
            if self._sha.get(name):
                body["sha"] = self._sha[name]
            code, resp = self._req("PUT", url, body)
            if code == 409:  # sha desactualizado
                self._refresh_sha(name)
                if self._sha.get(name):
                    body["sha"] = self._sha[name]
                code, resp = self._req("PUT", url, body)
            if code in (200, 201):
                self._sha[name] = resp["content"]["sha"]
                self._hash[name] = h
                self.last_error = None
            else:
                self.last_error = f"save {name}: {code} {(resp or {}).get('message', resp)}"
        except Exception as e:
            self.last_error = f"save {name}: {e}"

    def describe(self) -> str:
        p = f"/{self.prefix}" if self.prefix else ""
        return f"GitHub — {self.repo}@{self.branch}{p}"


# --------------------------------------------------------------------------- #
#  Fábrica                                                                     #
# --------------------------------------------------------------------------- #

def make_store(local_dir: str, token: str | None = None,
               repo: str | None = None, branch: str = "app-data",
               prefix: str = "") -> LocalStore | GitHubStore:
    if token and repo:
        return GitHubStore(token, repo, branch, prefix)
    return LocalStore(local_dir)
