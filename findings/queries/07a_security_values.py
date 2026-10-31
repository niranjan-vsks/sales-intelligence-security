"""Section 7.4 step 1: pull every value in the file that the provider itself classifies as a
security product, plus WAF names, and the http component -> category map, so the
what-we-sell list is built from values present, with their source column."""
from common import TAG, connect, out

con = connect()
con.execute(f"""COPY (SELECT comp, cat, count(*) n FROM (
    SELECT unnest(http_components) comp, http_component_cats cats FROM b
    WHERE len(http_components) > 0), LATERAL (SELECT unnest(cats) cat)
  GROUP BY 1, 2 ORDER BY n DESC) TO '{out('values/http_component_category_pairs.csv').as_posix()}' (HEADER)""")
print(TAG)
