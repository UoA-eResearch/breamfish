# Runbook

How the site is deployed and what to do when something looks wrong. Server configuration is not in this repo: it lives in a private Puppet control repo, in `site::profile::breamfish` (the app) and `site::profile::breamfish_web` (nginx and the certificate).

## How a change reaches the site

1. Merge to `main`.
2. CI tests, builds the frontend and pushes the result to the `release` branch (source, a hash-pinned `requirements.txt`, `web/dist`, and `SOURCE_COMMIT`).
3. The server's Puppet agent runs every 30 minutes. It moves the checkout at `/srv/breamfish/app` to the head of `release`, installs any changed dependencies into `/srv/breamfish/venv`, and starts a refresh.

To deploy immediately, run the agent on the server:

```bash
sudo puppet agent --test
```

To see what is deployed:

```bash
cat /srv/breamfish/app/SOURCE_COMMIT
```

To roll back, pin `site::profile::breamfish::revision` to an earlier commit of the `release` branch in the node's Hiera file, or revert on `main` and let CI publish again.

## On the server

| Thing | Where |
|---|---|
| App checkout (release branch) | `/srv/breamfish/app` |
| Python environment | `/srv/breamfish/venv` |
| Pipeline cache and output | `/var/lib/breamfish/cache`, `/var/lib/breamfish/published` |
| Settings and keys | `/etc/breamfish/env` (written by Puppet from eyaml) |
| Units | `breamfish-refresh.service`, `breamfish-refresh.timer` |
| Web server | nginx; vhosts under `/etc/nginx/sites-available/` |
| Certificate | `/etc/letsencrypt/live/<hostname>/`, renewed by `certbot.timer` |

Everything in that table is managed by Puppet. A change made by hand is undone at the next agent run, so change the Puppet code instead.

## Checks

```bash
systemctl list-timers 'breamfish*' certbot.timer     # when things next run
journalctl -u breamfish-refresh.service -n 30         # last pipeline runs
sudo systemctl start breamfish-refresh.service        # run the pipeline now
curl -s https://breamfishing.sonka.cloud.edu.au/data/status.json
sudo certbot certificates                             # certificate and expiry
sudo nginx -t                                         # config test
```

From anywhere:

```bash
curl -sI https://breamfishing.sonka.cloud.edu.au | head -1
echo | openssl s_client -connect breamfishing.sonka.cloud.edu.au:443 2>/dev/null | openssl x509 -noout -issuer -enddate
```

## When something is wrong

**The freshness badge says "out of date".** The pipeline has not published for over two hours. Check the journal for `breamfish-refresh.service`. A single source being down does not cause this: the pipeline reuses a cached copy for up to 12 hours and marks the source as stale in `status.json`.

**A source is marked stale.** Usually the upstream service is briefly down. Nothing to do unless it lasts; the About panel shows which source.

**The site is down but the server is up.** `sudo nginx -t`, then `systemctl status nginx`. Then run the Puppet agent, which restores managed files.

**The certificate is close to expiry.** `sudo certbot renew --dry-run` shows why renewal is failing. Renewal needs port 80 open from the internet.

**A deploy did not arrive.** Check that CI passed and that `release` moved, then run the agent with `--test` and read its output. The dependency install is hash-checked and will refuse a wheel that does not match `requirements.txt`.

## Network

The site needs TCP 80 and 443 open from the internet (80 for certificate renewal and the redirect) and nothing else inbound except SSH. On OpenStack that is one security group:

```bash
openstack security group create breamfish-web --description "HTTP and HTTPS for the breamfish site"
openstack security group rule create breamfish-web --protocol tcp --dst-port 80 --remote-ip 0.0.0.0/0
openstack security group rule create breamfish-web --protocol tcp --dst-port 443 --remote-ip 0.0.0.0/0
```

The server makes outbound HTTPS requests to Open-Meteo, LINZ, GitHub and PyPI.

## Setting up a server from scratch

What it took the first time, in order. The Puppet side is the two profiles named at the top; these are the steps around them.

1. **Network.** One interface on a network that can reach the Puppet server, a public address on it, and the security group above plus SSH. A second interface with its own default route makes replies leave by the wrong one; use one.
2. **Agent.** `sudo apt-get install puppet-agent`, then set `server` and `certname` in `/etc/puppet/puppet.conf`. If the Puppet server's public name is not reachable from the VM, pin it to the reachable address in `/etc/hosts` first (the profile keeps that entry afterwards).
3. **Certificate request.** `sudo puppet ssl submit_request` on the VM, then on the Puppet server compare the fingerprint in `puppetserver ca list` and sign it.
4. **Check the HTTP challenge before the real thing.** With nothing listening on port 80 yet: `sudo certbot certonly --standalone --dry-run -d <hostname> --non-interactive --agree-tos --register-unsafely-without-email`. This uses Let's Encrypt's staging service and saves nothing.
5. **First runs.** `sudo puppet agent --test --noop`, read what it would do, then run it without `--noop`. A second run should report no changes.

Things that bit, so they do not bite again:

- **Ubuntu's stock `nginx.conf` already sets `server_tokens`.** nginx rejects a second one in `conf.d`, so the vhosts set it themselves.
- **Ubuntu's own `puppet-agent` package installs the service disabled.** The profile manages `puppet.service`; without that nothing re-checks the node or deploys releases.
- **The agent here is Puppet 8.10 and the server was 7.17.** That pairing is not officially supported. It worked for this catalog; re-test with `--noop` after upgrading either side.

## Refreshing committed assets

```bash
python3 scripts/fetch_static_layers.py    # marine reserve and boat ramp layers
scripts/make_basemap.sh                   # map tiles, fonts and icons (needs the pmtiles CLI)
```

Both write into `web/public/`. Review the diff and commit.

The seabed grids are rebuilt the same way, by hand, and need the development dependencies and a LINZ Data Service key in your shell:

```bash
export LINZ_API_KEY=...                  # never commit it
uv run python scripts/build_seabed.py    # writes web/public/seabed/ and docs/seabed-report.md
```

Sources are cached under `data/seabed/raw/`, so a second run needs no network. Read `docs/seabed-report.md` before committing: it compares the new grids with charted soundings. See [seabed.md](seabed.md).
