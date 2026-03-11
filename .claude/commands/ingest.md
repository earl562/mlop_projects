Ingest a municipality's zoning ordinances into PlotLot's vector database.

## Usage

Provide the municipality name as an argument: `/ingest Miami Beach`

## Steps

1. Verify the municipality is discoverable on Municode:
   ```bash
   cd plotlot && uv run plotlot-search --list-municipalities | grep -i "$ARGUMENTS"
   ```

2. Run the ingestion pipeline:
   ```bash
   cd plotlot && uv run plotlot-ingest --municipality "$ARGUMENTS"
   ```
   This will: scrape ordinance pages → chunk text → generate NVIDIA embeddings (1024d) → store in pgvector

3. Verify ingestion:
   ```bash
   cd plotlot && uv run plotlot-search --municipality "$ARGUMENTS" --query "residential zoning density" --limit 3
   ```

4. Report: number of chunks ingested, any errors during scraping/embedding, sample search result quality.

## Alternatively, use the API (for remote/production):

```bash
curl -X POST https://plotlot-api.onrender.com/admin/ingest \
  -H "Content-Type: application/json" \
  -d '{"municipality": "$ARGUMENTS"}'
```

## Currently Ingested (5 municipalities):
- Miami Gardens (3,561 chunks)
- Miami-Dade County (2,666 chunks)
- Boca Raton (1,538 chunks)
- Miramar (241 chunks)
- Fort Lauderdale (136 chunks)
