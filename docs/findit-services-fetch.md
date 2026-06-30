# Fetching FindIt Services

The `_fetch_services` function in `migration_oracle/paysafe/findit.py` acts as an HTTP client for retrieving the list of registered services from the Paysafe FindIt registry.

## Details

- **URL:** `{FINDIT_BASE_URL}/services` (e.g. `https://findit.paysafe.com/api/v1/services` - base URL depends on the `config.FINDIT_BASE_URL` value).
- **Request Method:** `GET`
- **Query Parameters:** None.
- **Headers:** 
  - `Authorization: Bearer <FINDIT_AUTH_TOKEN>` (Only included if `config.FINDIT_AUTH_TOKEN` is configured).
- **Timeouts & Retries:** Uses a 10-second timeout per request. It automatically retries on timeout or HTTP errors up to 2 times, with backoffs of 1.0s and 3.0s respectively.

## Response Body

The function parses the JSON response and supports two different payload structures from the API:
1. **JSON Array (List):** Returns the list directly if the payload is an array.
   ```json
   [
     { "name": "service-a", "codeRepoLink": "https://github.com/paysafe/service-a" },
     { "name": "service-b", "codeRepoLink": "https://github.com/paysafe/service-b" }
   ]
   ```
2. **JSON Object (Dict):** Extracts the array from the `services` key if the payload is an object.
   ```json
   {
     "services": [
       { "name": "service-a", "codeRepoLink": "https://github.com/paysafe/service-a" }
     ]
   }
   ```
If the payload format is unrecognized or the `services` key is missing/invalid, it defaults to an empty list `[]`.

## What We Are Using It For

We are using this endpoint to **bulk load the entire registry of Paysafe services into memory**. 

This data is cached locally for 30 days (`_CACHE_TTL_DAYS`) and used to map internal service names to their corresponding source code repository URLs (`codeRepoLink`). The `migration_oracle` relies on this repository mapping when trying to locate and process projects during automated framework migrations. It uses four levels of matching (exact, case-insensitive, alphanumeric-normalized, and fuzzy) to tolerate slight discrepancies in service names.
