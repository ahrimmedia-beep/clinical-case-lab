-- Points distribution of the cohort (AI players excluded) for the percentile curve;
-- every bin 0..max_points is present.
WITH bins AS (
    SELECT generate_series(0, CAST(:max_points AS integer)) AS points
),
counts AS (
    SELECT a.points, count(*) AS n
    FROM attempts AS a
    WHERE a.case_id = :case_id
      AND coalesce(a.simulated_label, '') NOT LIKE 'ai:%'
    GROUP BY a.points
)
SELECT b.points, coalesce(c.n, 0) AS n
FROM bins AS b
LEFT JOIN counts AS c ON c.points = b.points
ORDER BY b.points
