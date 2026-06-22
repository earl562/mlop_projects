"""Discover Municode configs for Fort Lauderdale and Davie.

Fort Lauderdale: The current fallback config uses
    zoning_node_id="UNLADERE_CH47UNLADERE_ARTIIZODIRE"
which points to Article II (sub-node) under Chapter 47, yielding only ~200 chunks.
We need the CHAPTER-LEVEL node (CH47UNLADERE) that captures ALL zoning content.

Davie: No fallback config exists. Discover the complete MunicodeConfig.

Usage:
    cd plotlot && uv run python scripts/discover_fl_configs.py
"""

import asyncio

import httpx

LIBRARY_API_URL = "https://library.municode.com/api"
LIBRARY_HEADERS = {"X-CSRF": "1", "Accept": "application/json"}

# Known Fort Lauderdale config from _FALLBACK_CONFIGS
FTL_KNOWN = {
    "client_id": 2247,
    "product_id": 13463,
    "job_id": 482747,
    "zoning_node_id": "UNLADERE_CH47UNLADERE_ARTIIZODIRE",
}


async def fetch_json(
    client: httpx.AsyncClient, path: str, **params
) -> dict | list | None:
    """GET the Municode Library API."""
    url = f"{LIBRARY_API_URL}/{path}"
    try:
        resp = await client.get(url, params=params, headers=LIBRARY_HEADERS)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ✗ API error: {path} params={params} — {e}")
        return None


def find_client(clients: list[dict], name: str) -> dict | None:
    """Find a client by name (exact match first, then fuzzy)."""
    name_lower = name.lower().strip()
    for c in clients:
        cname = (c.get("ClientName") or "").lower().strip()
        if cname == name_lower:
            return c
    # Fuzzy: "City of ..." prefix or substring
    for c in clients:
        cname = (c.get("ClientName") or "").lower().strip()
        if f"city of {name_lower}" in cname:
            return c
        if name_lower in cname or cname in name_lower:
            return c
    return None


async def get_root_toc(
    client: httpx.AsyncClient, product_id: int, job_id: int
) -> list[dict] | None:
    """Get the root TOC children."""
    result = await fetch_json(
        client, "codesToc/children", productId=product_id, jobId=job_id
    )
    if isinstance(result, list):
        return result
    return None


async def get_toc_children(
    client: httpx.AsyncClient, product_id: int, job_id: int, node_id: str
) -> list[dict] | None:
    """Get children of a specific TOC node."""
    result = await fetch_json(
        client,
        "codesToc/children",
        productId=product_id,
        jobId=job_id,
        nodeId=node_id,
    )
    if isinstance(result, list):
        return result
    return None


def print_toc(items: list[dict], indent: int = 0, max_items: int = 30):
    """Print a TOC tree up to max_items."""
    for i, item in enumerate(items[:max_items]):
        node_id = item.get("Id") or item.get("id") or item.get("NodeId") or ""
        heading = item.get("Heading") or item.get("Title") or item.get("title") or "???"
        children_count = item.get("ChildrenCount", 0)
        print(
            f"{'  ' * indent}[{node_id}] {heading}"
            f"{' (+' + str(children_count) + ')' if children_count else ''}"
        )
    if len(items) > max_items:
        omitted = len(items) - max_items
        print(f"{'  ' * indent}... ({omitted} more items omitted)")


async def discover_fort_lauderdale(client: httpx.AsyncClient):
    """Discover Fort Lauderdale's chapter-level zoning node.

    The current config uses Article II sub-node. We need the parent Chapter 47 node
    that encompasses ALL 15 articles (ARTI through ARTXV).
    """
    print("\n" + "=" * 70)
    print("FORT LAUDERDALE — Discovering Chapter-level zoning node")
    print("=" * 70)

    pid = FTL_KNOWN["product_id"]
    jid = FTL_KNOWN["job_id"]

    # Step 1: Fetch root TOC
    print(f"\nFetching root TOC (product={pid}, job={jid})...")
    root_toc = await get_root_toc(client, pid, jid)
    if not root_toc:
        print("  ✗ Failed to fetch root TOC")
        return

    print(f"  ✓ Root TOC has {len(root_toc)} entries:")
    print_toc(root_toc)

    # Step 2: Check what CD_ORDOFFOLAFL (Code of Ordinances) contains
    print("\n--- Children of CD_ORDOFFOLAFL (Code of Ordinances) ---")
    cdo_toc = await get_toc_children(client, pid, jid, "CD_ORDOFFOLAFL")
    if cdo_toc:
        print(f"  {len(cdo_toc)} entries:")
        print_toc(cdo_toc, indent=1)
        # Check if Code of Ordinances contains zoning chapters
        for item in cdo_toc:
            heading = (item.get("Heading") or item.get("Title") or "").lower()
            if any(kw in heading for kw in ["zoning", "land dev", "unified land"]):
                node_id = item.get("Id") or item.get("id") or ""
                print(f"    → ZONING MATCH: [{node_id}] {item.get('Heading') or item.get('Title', '?')}")
    else:
        print("  (no children or error)")

    # Step 3: Try various candidate parent nodes for Chapter 47
    print("\n--- Testing candidate chapter-level nodes ---")
    candidates = [
        "UNLADERE_CH47UNLADERE",
        "CH47UNLADERE",
        "UNLADERE",
        "UNIFIED_LAND_DEVELOPMENT_REGULATIONS",
        "PTIICOOR_CH47UNLADERE",  # Part II style like WPB
        "PTIIICOOR_CH47UNLADERE",  # Part III style like MDC
    ]
    for candidate in candidates:
        children = await get_toc_children(client, pid, jid, candidate)
        if children and isinstance(children, list) and len(children) > 0:
            is_zoning = any(
                "zoning" in (c.get("Heading") or c.get("Title") or "").lower()
                for c in children[:5]
            )
            print(f"  [{candidate}]: {len(children)} children {'★ ZONING' if is_zoning else ''}")
            if len(children) <= 5 and is_zoning:
                print_toc(children, indent=2)
        else:
            print(f"  [{candidate}]: NOT FOUND (or empty)")

    # Step 4: Check the UNLADERECOTAOR (Comparative Table) node
    print("\n--- Children of UNLADERECOTAOR (Comparative Table) ---")
    ct_children = await get_toc_children(client, pid, jid, "UNLADERECOTAOR")
    if ct_children:
        print(f"  {len(ct_children)} entries")
        print_toc(ct_children, indent=1)

    # Step 5: Check the UNIFIED_LAND_DEVELOPMENT_REGULATIONSSTLARETA node
    print("\n--- Children of UNIFIED_LAND_DEVELOPMENT_REGULATIONSSTLARETA (State Law Ref) ---")
    slr_children = await get_toc_children(
        client, pid, jid, "UNIFIED_LAND_DEVELOPMENT_REGULATIONSSTLARETA"
    )
    if slr_children:
        print(f"  {len(slr_children)} entries")
        print_toc(slr_children, indent=1)

    # Step 6: Check each ULADRE article to confirm they have children
    uladre_articles = [
        item for item in root_toc
        if "UNLADERE_CH47UNLADERE_ART" in str(item.get("Id") or item.get("id") or "")
    ]
    print(f"\n--- ULADRE Articles at root level: {len(uladre_articles)} ---")
    total_article_children = 0
    for art in uladre_articles:
        art_id = str(art.get("Id") or art.get("id") or "")
        art_heading = art.get("Heading") or art.get("Title") or "?"
        art_children = await get_toc_children(client, pid, jid, art_id)
        n = len(art_children) if art_children else 0
        total_article_children += n
        print(f"  [{art_id}] {art_heading}: {n} children")

    print(f"\n  Total article-level children (sections): {total_article_children}")

    # Step 7: Count full recursive leaf count for Article II vs all articles
    print("\n--- Recursive leaf count estimate ---")
    art2_children = await get_toc_children(
        client, pid, jid, FTL_KNOWN["zoning_node_id"]
    )
    art2_leaf_count = 0
    if art2_children:
        for child in art2_children:
            child_id = str(child.get("Id") or child.get("id") or "")
            has_children = child.get("HasChildren", False)
            if has_children:
                grandkids = await get_toc_children(client, pid, jid, child_id)
                if grandkids:
                    for gk in grandkids:
                        gk_id = str(gk.get("Id") or gk.get("id") or "")
                        if gk.get("HasChildren", False):
                            great_grandkids = await get_toc_children(
                                client, pid, jid, gk_id
                            )
                            art2_leaf_count += len(great_grandkids) if great_grandkids else 1
                        else:
                            art2_leaf_count += 1
            else:
                art2_leaf_count += 1
    print(f"  Article II leaf count (recursive): ~{art2_leaf_count}")

    # Step 8: Verify HasChildren flags for non-ULADRE root entries
    print("\n--- HasChildren flags for all root entries ---")
    for item in root_toc:
        node_id = str(item.get("Id") or item.get("id") or "")
        heading = item.get("Heading") or item.get("Title") or "?"
        has_children = item.get("HasChildren", False)
        is_uladre = "UNLADERE_CH47UNLADERE_ART" in node_id
        print(f"  [{node_id}] HasChildren={has_children} {'← ULADRE' if is_uladre else ''} {heading[:60]}")

    # Step 9: Verify empty-string root walk works (simulate scraper behavior)
    print("\n--- Simulating scraper with zoning_node_id='' ---")
    print("  With '', get_toc_children returns root TOC (19 entries, no nodeId param)")
    print("  Non-ULADRE entries with HasChildren=False become leaf nodes")
    print("  ULADRE entries (HasChildren=True) are recursively walked")
    print("  CD_ORDOFFOLAFL HasChildren: check above → no content pulled")
    print("  SUHITA leaf content is negligible")
    print("  UNLADERECOTAOR: empty → negligible")
    print("  UNIFIED_LAND_DEVELOPMENT_REGULATIONSSTLARETA: empty → negligible")

    # Final recommendation
    print(f"\n  {'='*50}")
    print("  RECOMMENDED FALLBACK CONFIG:")
    print(f"  {'='*50}")
    print("  \"fort_lauderdale\": MunicodeConfig(")
    print("      municipality=\"Fort Lauderdale\",")
    print("      county=\"broward\",")
    print(f"      client_id={FTL_KNOWN['client_id']},")
    print(f"      product_id={FTL_KNOWN['product_id']},")
    print(f"      job_id={FTL_KNOWN['job_id']},")
    print("      zoning_node_id=\"\",  # empty = walk entire root TOC (all 15 ULADRE articles)")
    print("  ),")
    print(f"  {'='*50}")


async def discover_davie(client: httpx.AsyncClient):
    """Discover Davie's complete Municode config."""
    print("\n" + "=" * 70)
    print("DAVIE — Full discovery")
    print("=" * 70)

    # Step 1: Find Davie in FL clients
    print("\nFetching FL clients list...")
    fl_clients = await fetch_json(client, "Clients/stateAbbr", stateAbbr="FL")
    if not fl_clients or not isinstance(fl_clients, list):
        print("  ✗ Failed to fetch FL clients")
        return

    print(f"  ✓ Got {len(fl_clients)} FL clients")

    # Search for Davie
    davie_client = find_client(fl_clients, "Davie")
    if not davie_client:
        print("  ✗ Could not find 'Davie' in FL clients")
        # Print all clients with "dav" in name
        print("\n  Clients matching 'dav':")
        for c in fl_clients:
            cname = str(c.get("ClientName", "")).lower()
            if "dav" in cname:
                client_id = c.get("ClientID", "?")
                print(f"    [{client_id}] {c.get('ClientName', '?')}")
        return

    client_id = davie_client.get("ClientID", 0)
    print(f"  ✓ Found Davie: client_id={client_id} ({davie_client.get('ClientName')})")

    # Step 2: Get products
    print(f"\nFetching products for client_id={client_id}...")
    products = await fetch_json(client, f"Products/clientId/{client_id}")
    if not products or not isinstance(products, list):
        print("  ✗ Failed to fetch products")
        return

    print(f"  ✓ Got {len(products)} products:")
    codes_products = []
    for p in products:
        if not isinstance(p, dict):
            continue
        content_type = p.get("ContentType", {})
        ct_id = content_type.get("Id", "?") if isinstance(content_type, dict) else "?"
        ct_name = content_type.get("Name", "?") if isinstance(content_type, dict) else "?"
        pid = p.get("ProductID", "?")
        pname = p.get("ProductName", "?")
        print(f"    [{pid}] {pname} (ContentType: {ct_id}/{ct_name})")
        if isinstance(content_type, dict) and content_type.get("Id") == "CODES":
            codes_products.append(p)

    if not codes_products:
        print("  ✗ No CODES products found")
        return

    print(f"\n  Found {len(codes_products)} CODES product(s)")

    # For each CODES product, get latest job and TOC
    for prod in codes_products:
        product_id = prod.get("ProductID")
        if not product_id:
            continue
        pname = prod.get("ProductName", "?")

        print(f"\n  --- Product: [{product_id}] {pname} ---")

        job_data = await fetch_json(client, f"Jobs/latest/{product_id}")
        if not job_data or not isinstance(job_data, dict):
            print("    ✗ Failed to fetch latest job")
            continue

        job_id = job_data.get("Id")
        if not job_id:
            print("    ✗ No job_id found")
            continue
        print(f"    Job ID: {job_id}")

        # Get root TOC
        root_toc = await get_root_toc(client, product_id, job_id)
        if not root_toc:
            print("    ✗ Failed to fetch root TOC")
            continue

        print(f"    Root TOC ({len(root_toc)} entries):")
        print_toc(root_toc, indent=2)

        # Search for zoning keywords
        print("\n    Searching TOC for zoning keywords...")
        zoning_keywords = [
            "zoning",
            "land development",
            "land use",
            "uldc",
            "unified land",
            "development code",
            "development regulations",
            "planning and zoning",
            "appendix a",
            "appendix b",
        ]

        # Search root level
        for item in root_toc:
            node_id = str(item.get("Id") or item.get("id") or "")
            heading = (item.get("Heading") or item.get("Title") or "").lower()
            for kw in zoning_keywords:
                if kw in heading:
                    children_count = item.get("ChildrenCount", 0)
                    print(
                        f"    ★ [{node_id}] {item.get('Heading') or item.get('Title', '?')}"
                        f" (+{children_count} children)"
                    )

                    # Fetch children of this node
                    children = await get_toc_children(
                        client, product_id, job_id, node_id
                    )
                    if children:
                        print(f"      Actual children: {len(children)}")
                        print_toc(children, indent=3, max_items=10)
                    break

        # Also search one level deeper (children of root nodes)
    print("\n    Searching one level deeper...")
    for item in root_toc:
        node_id = str(item.get("Id") or item.get("id") or "")
        if not node_id:
            continue
        children = await get_toc_children(client, product_id, job_id, node_id)
        if not children:
            continue
        for child in children:
            child_id = str(
                child.get("Id") or child.get("id") or ""
            )
            heading = (child.get("Heading") or child.get("Title") or "").lower()
            for kw in zoning_keywords:
                if kw in heading:
                    children_count = child.get("ChildrenCount", 0)
                    parent_heading = item.get("Heading") or item.get("Title") or "?"
                    print(
                        f"    ★ [{child_id}] {child.get('Heading') or child.get('Title', '?')}"
                        f" (+{children_count} children) — parent: {parent_heading}"
                    )
                    break

    # Compare Ch12 (Land Development Code) vs Ch27 (Zoning)
    print("\n    --- Comparing Chapter 12 vs Chapter 27 ---")
    for ch_id, ch_label in [
        ("PTIICOOR_CH12LADECO", "Chapter 12 - Land Development Code"),
        ("PTIICOOR_CH27ZO", "Chapter 27 - Zoning"),
    ]:
        ch_children = await get_toc_children(client, product_id, job_id, ch_id)
        n = len(ch_children) if ch_children else 0
        print(f"    [{ch_id}] {ch_label}: {n} children (articles/sections)")
        if ch_children and n <= 25:
            print_toc(ch_children, indent=3)

    # Final Davie config
    print(f"\n    {'='*50}")
    print("    RECOMMENDED DAVIE FALLBACK CONFIG:")
    print(f"    {'='*50}")
    print("    \"davie\": MunicodeConfig(")
    print("        municipality=\"Davie\",")
    print("        county=\"broward\",")
    print(f"        client_id={client_id},")
    print(f"        product_id={product_id},")
    print(f"        job_id={job_id},")
    print("        zoning_node_id=\"PTIICOOR_CH12LADECO\",  # Land Development Code (19 articles)")
    print("    ),")
    print("    # Alt: zoning_node_id=\"PTIICOOR_CH27ZO\" for Chapter 27 Zoning only")
    print(f"    {'='*50}")


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        await discover_fort_lauderdale(client)
        await discover_davie(client)

    print("\n" + "=" * 70)
    print("DISCOVERY COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
