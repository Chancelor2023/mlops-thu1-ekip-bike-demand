# Lab 7 — Quality gate: défauts et tests de régression

Le dépôt complet n'était pas disponible dans les fichiers montés. Les cas ci-dessous sont implémentés dans `tests/test_gate.py`; leurs résultats observés doivent être complétés après l'exécution dans un environnement disposant des dépendances de projet.

| Défaut / scénario | Test | Résultat attendu | Résultat observé | Explication |
|---|---|---|---|---|
| Checksum dataset différent du manifeste et des metadata | `test_modified_dataset_checksum_blocks` | blocked | À exécuter | Le digest calculé doit concorder avec le manifeste et le snapshot déclaré. |
| Features réordonnées | `test_reordered_features_block` | blocked | À exécuter | Le contrat des 12 features est vérifié dans l'ordre exact. |
| Preuves de l'accepté manquantes | `test_missing_accepted_proof_blocks` | blocked | À exécuter | Un comparatif qualité/performance sans modèle, metadata et metrics acceptés n'est pas recevable. |
| Prédictions négatives ou non finies | `test_negative_or_nonfinite_predictions_block` | blocked | À exécuter | Sorties invalides constituent une défaillance d'intégrité. |
| Candidat moins bon que la moyenne train | `test_candidate_worse_than_train_mean_is_rejected` | rejected | À exécuter | La MAE doit être strictement inférieure au baseline train-mean sur validation. |
| Candidat pire que l'accepté de plus que epsilon | `test_candidate_worse_than_accepted_by_more_than_epsilon_is_rejected` | rejected | À exécuter | Comparaison faite sur les mêmes lignes validation, avec epsilon=1e-6. |
| Égalité au bord accepté + epsilon | `test_candidate_at_accepted_plus_epsilon_is_eligible` | eligible, mention d'équivalence | À exécuter | Le seuil accepté est inclusif; l'écart dans epsilon ne doit pas être présenté comme une amélioration. |
| Latence supérieure à 1.25× accepté | `test_latency_over_25_percent_is_rejected` | rejected | À exécuter | Le callable injecté simule les mesures sans Cloud Run. |
| Checksum du modèle modifié | `test_tampered_model_checksum_blocks` | blocked | À exécuter | Le digest réel ne correspond plus au sha256 enregistré dans metadata. |
| Metrics candidat absentes | `test_missing_candidate_metrics_blocks` | blocked | À exécuter | Une exécution incomplète ne peut pas passer le gate. |
| Accepted immuable après décisions rejected/blocked | `test_accepted_tree_hash_unchanged_after_rejected_or_blocked` | hash avant/après identique | À exécuter | Le gate ne modifie jamais les artefacts acceptés. |
| Eligible ne déclenche aucune promotion | `test_eligible_random_forest_on_same_validation_and_no_promotion` | aucun artefact accepté modifié/créé | À exécuter | La promotion est hors de la responsabilité du gate. |
