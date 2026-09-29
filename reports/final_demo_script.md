# Offline demo script

1. Start `streamlit run app/streamlit_app.py`.
2. Upload `samples/demo/construction_fire_door.txt`, choose Construction, and extract evidence.
3. Show the findings table, then correct one span and save it. Open Correction history.
4. Repeat with `aviation_sdr.txt` and Aviation; show assertion status and the provisional NER option.
5. Repeat with `pipeline_incident.txt` and Pipeline; show component, cause, material, and action.
6. Show Analytics and Saved model evaluations. State that classification scores are source-specific
   and all NER/hybrid metrics are provisional.
7. Export JSON or CSV. The samples are synthetic and contain no downloaded narratives.
