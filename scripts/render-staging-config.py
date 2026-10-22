#!/usr/bin/env python3
"""Render staging configuration."""

import argparse
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def read_domains(path):
    names = {"BASE_DOMAIN", "STAGING_SUBDOMAIN"}
    values = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in names or name in values:
            raise ValueError("domain config accepts one BASE_DOMAIN and one STAGING_SUBDOMAIN assignment")
        values[name] = value.strip()

    if set(values) != names:
        raise ValueError("domain config requires BASE_DOMAIN and STAGING_SUBDOMAIN")

    base = values["BASE_DOMAIN"]
    labels = base.split(".")
    if len(base) > 253 or len(labels) < 2 or any(not DNS_LABEL.fullmatch(label) for label in labels):
        raise ValueError("BASE_DOMAIN must be a lowercase DNS hostname without scheme, port or wildcard")
    subdomain = values["STAGING_SUBDOMAIN"]
    if not DNS_LABEL.fullmatch(subdomain):
        raise ValueError("STAGING_SUBDOMAIN must be a single lowercase DNS label")

    staging = f"{subdomain}.{base}"
    if len(staging) > 253:
        raise ValueError("derived STAGING_DOMAIN exceeds the DNS hostname length limit")
    return values | {"STAGING_DOMAIN": staging}


def render(text, domains):
    # Keep Traefik's ${2} untouched.
    replacements = domains | {
        "BASE_DOMAIN_REGEX": re.escape(domains["BASE_DOMAIN"]),
        "STAGING_DOMAIN_REGEX": re.escape(domains["STAGING_DOMAIN"]),
    }
    rendered = text
    for name, value in replacements.items():
        rendered = rendered.replace("${" + name + "}", value)
    if any("${" + name in rendered for name in domains):
        raise ValueError("unrecognized domain placeholder")
    return "# Generated file.\n" + rendered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "deploy/staging.env")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/staging")
    args = parser.parse_args()

    try:
        domains = read_domains(args.config)
        sources = {Path(".env.staging.example"): ROOT / ".env.staging.example"}
        for source in sorted((ROOT / "deploy/traefik/dynamic/staging").glob("*.yaml")):
            sources[Path("traefik/dynamic") / source.name] = source

        output = args.output_dir.resolve()
        if any((output / relative).resolve() == source.resolve() for relative, source in sources.items()):
            raise ValueError("output directory would overwrite a source template")

        # Render before writing files.
        rendered = {relative: render(source.read_text(), domains) for relative, source in sources.items()}
        domain = domains["STAGING_DOMAIN"]
        public_values = domains | {
            "FRONTEND_PUBLIC_URL": "https://" + domain,
            "INSTITUTIONAL_BASE_DOMAIN": domain,
            "WEBAUTHN_RP_ID": domain,
            "WEBAUTHN_ALLOWED_ORIGINS": "https://" + domain,
            "EMAIL_VERIFICATION_FRONTEND_URL": "https://" + domain,
            "PASSWORD_RECOVERY_FRONTEND_URL": "https://" + domain,
        }
        rendered[Path("domains.env")] = "# Public values only.\n" + "".join(
            f"{name}={value}\n" for name, value in public_values.items()
        )
        for relative, content in rendered.items():
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Avoid partial config files.
            with tempfile.NamedTemporaryFile(mode="w", dir=destination.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    stream.write(content)
                    stream.flush()
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
    except (OSError, ValueError) as error:
        print(f"Cannot render staging configuration: {error}", file=sys.stderr)
        return 1

    print(f"Rendered {len(rendered)} public configuration files in {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
