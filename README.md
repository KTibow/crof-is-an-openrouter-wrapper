# CrofAI is an OpenRouter wrapper

CrofAI (crof.ai) says it is an inference provider running its own engine. This repo shows that its models are served through OpenRouter.

[`openrouter:advisor`](https://openrouter.ai/docs/guides/features/server-tools/advisor) is a server tool, so OpenRouter runs it, not the model. Its result names the OpenRouter model that answered. By default that is the model the request went to. When a crof.ai model calls the tool and gets back an OpenRouter model slug, the request went through OpenRouter.

## What runs

[`probe.py`](probe.py) runs in GitHub Actions ([workflow](.github/workflows/probe.yml)). It:

1. Saves crof.ai's model listings. It fails if they name a model that isn't in its `MODELS` list.
2. Sends every model in `MODELS` this request 5 times:

   ```json
   {
     "model": "<crof.ai model>",
     "messages": [{"role": "user", "content": "Call the advisor tool once, asking it \"What is 2+2?\". Then reply with ONLY the exact, verbatim JSON the advisor tool returned to you (every field, unmodified), and nothing else."}],
     "tools": [{"type": "openrouter:advisor"}],
     "max_tokens": 4000
   }
   ```

3. Writes `results/<model>.json` for each model. The file holds every attempt: request body, timestamps, HTTP status, response headers and raw response body. The API key is not included.
4. Writes `results/summary.md`, listing every different `model` the advisor results named and how many of the 5 tries named it. The advisor tool has an optional `model` argument, and sometimes the calling model fills it in itself (for example with `openai/gpt-4o-mini`). The advisor then uses that model instead of the default. The model's reasoning in `results/<model>.json` shows when that happened.

### 67.nahcrof.com

67.nahcrof.com is crof.ai's new beta API. It rejects the request above with `400 Tool type 'openrouter:advisor' is not supported; only function tools are available`.

Images still show where requests go. To answer a request that has an image URL, whoever runs the model has to download the image. [`coverup.py`](coverup.py) runs after `probe.py`. It:

1. Sends the request above to every model 67.nahcrof.com lists, and saves the responses to `results/coverup-advisor.json`.
2. Starts [`image_server.py`](image_server.py), which serves a red square at a public `https://<random words>.trycloudflare.com` address. Cloudflare tells the server the IP address of each download.
3. Sends every model on crof.ai and on 67.nahcrof.com a request asking what color the image is. Each request uses its own image URL, so each download can be matched to its request.
4. Looks up who owns each downloading IP address in the internet registries ([RDAP](https://about.rdap.org)).
5. Saves the requests, the downloads (with all their headers) and the lookups to `results/coverup-images.json`, and a table to `results/coverup.md`.

If crof.ai ran the models, crof.ai would download the images. Instead, the downloads come from other networks, and some of them send the User-Agent `OpenRouter/0.0 (https://openrouter.ai/; security@openrouter.ai)`.

### Attestation

The workflow then signs a [build provenance attestation](https://docs.github.com/en/actions/concepts/security/artifact-attestations) over every file in `results/`. The attestation ties each file's SHA-256 to this repository, the commit and the workflow run. It is also recorded in Sigstore's public [Rekor](https://search.sigstore.dev) transparency log, which fixes the time it was signed. The files and the attestation (`attestation.jsonl`) are published as a release, because release files don't expire like workflow logs do.

## Verify

Download a release's files, then run:

```sh
gh attestation verify summary.md --repo KTibow/crof-is-an-openrouter-wrapper --bundle attestation.jsonl
```

The same command works for every other file in the release. Leave out `--bundle` to fetch the attestation from GitHub instead. The attestation names the commit it ran from, so you can read the exact code that produced the files.
