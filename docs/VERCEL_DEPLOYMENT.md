# Vercel demo deployment

Production: https://sih-prototype-bice.vercel.app

The `sih-prototype` Vercel project runs the FastAPI app with the Vite build.
`pyproject.toml` contains the API's runtime dependencies. The existing
`requirements.txt` retains the dependencies used for local processing.

Before deploying a new demo snapshot, run from the repository root:

```powershell
.venv/Scripts/python.exe scripts/prepare_vercel.py
vercel.cmd deploy --yes
```

The packaging script backs up `data/punarvaas.db` consistently, verifies it,
and creates `deployment-data/demo.db.gz`. This generated snapshot is excluded
from Git but uploaded by Vercel CLI through `.vercelignore`. Git-based automatic
deployments need a separate snapshot provisioning step.

After checking the deployment, publish the tested URL:

```powershell
vercel.cmd promote <deployment-url> --yes
.venv/Scripts/python.exe scripts/check_deployment.py https://sih-prototype-bice.vercel.app
```

The demo restores its bundled database to temporary storage on each new
serverless instance. District data remains in the immutable deployment
snapshot; new audit entries are temporary and are not shared between instances.
Run processing pipelines locally and repackage to publish new results.

For persistent storage, configure a populated Turso database using
`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. The Turso adapter takes precedence
over the bundled demo. Credentials belong in Vercel environment settings.
