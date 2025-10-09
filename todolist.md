# General
    * [X] ~~*project file created*~~ [2025-09-24]
    * [X] ~~*github sync*~~ [2025-09-24]

# Traffic Prediction
    * [X] ~~*Dataset from AT*~~ [2025-09-24]
    * [X] ~~*Dataset Cleaning*~~ [2025-09-24] 
    * [X] ~~*XGBoost implementation*~~ [2025-09-24]
    * [X] ~~*Automatic outlier detection*~~ [2025-09-24]
    * [X] ~~*remove timestamp that have continuos zero volume*~~ [2025-09-24]
    * [X] ~~*add spatial feature, turning traffic and direction*~~ [2025-09-24]
    
# XAI Implementation (SHAP)
    * [X] ~~*SHAP Implementation*~~ [2025-09-24]

# Hotspot Detection
    * [X] ~~*KPI Table - rank sites by congestion severity*~~ [2025-09-29]
      * [X] ~~*site level*~~ [2025-09-29] 
        - Rank site by site-level 95th percentile utilization
        - For the top K sites, build lane level table to see which lanes drive the problem
      * [X] ~~*lane level (for policy design)*~~ [2025-09-29]
    * [ ] SHAP plot - explain why those sites congest
    * [X] ~~*Visualize hotspots on a map/diagram*~~ [2025-09-29]
    * [ ] Automate peak-hour vs off-peak comparison
    * [X] ~~*Select top 3 most congestion site for LLM input*~~ [2025-09-29]

# Simulation (Optional)
    * [X] ~~*Export hotspot to SUMO*~~ [2025-09-30]
    * [ ] Clean hotspot (1 done 2 to go)
    * [X] ~~*Run basic simulation*~~ [2025-10-01]
    * [X] ~~*Extract simulation KPI (Queue Length, Travel Time)*~~ [2025-10-07]
    * [ ] Use dataset for traffic generation     

# LLM Policy Creation
    * [X] ~~*Design prompt template*~~ [2025-10-07]
          "Given KPI = [x], context =  [y], SHAP insight = [z], recommend traffic policy
    * [X] ~~*OUTPUT: Policy Recommendations*~~ [2025-10-07]
    * [ ] include XAI result

# Traffic Validation
    * [ ] Replicate the top 3 most congestion sites, with sensor
    * [X] ~~*Implement policy recommendations*~~ [2025-10-07] 
    * [ ] Define Validation Metric 
    * [ ] Validate the policy

* [ ] organize source code
    * [X] ~~*traffic simulation result - date indexed*~~ [2025-10-09]
    * [X] ~~*LLM result - date indexed*~~ [2025-10-09]
    * [ ] road network - date indexed
* [ ] create traffic based on most congestion day
* [ ] edit LLM prompt - include XAI results
* [ ] run simulation



* [ ] strutural abstract (punchy)

* [ ] why is the problem important
* [ ] what the context
* [ ] how - an overview
* [ ] how much - what are our contribution worth (novelty, contribution)
* [ ] https://zenodo.org



4606
3869

8164
9168