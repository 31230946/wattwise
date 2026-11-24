Put the Low Carbon London file here (not included, ~600 MB):
  LCL_2013.csv  or  LCL_2013_kWh.csv.zip
Download: https://data.4tu.nl/datasets/fbbe775b-48d8-469f-a39b-b64488bfd6fd
Then: python3 train.py --real
(train.py writes household_data.csv here.)

INCLUDED: pune_sim_daily.csv = SIMULATED Pune homes (real LCL homes reshaped to published
Prayas Pune averages). Demo and stress test only, never real Indian data.
See pune_sim/PUNE_SIM.md.
