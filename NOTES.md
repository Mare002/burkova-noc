NOTES

Predpoklady

1. Label rozhoduje podľa toho, s čím volajúci odišiel. Priorita: úspešné prepojenie > hlásenie > neúspešné prepojenie > oznámená porucha > odkázanie inam > chyba nástroja > adresa > ENDED_EARLY.
2. Volajúci je „informovaný“, len ak get_outage vrátil poruchu a bot prehovoril pred zložením. Ak volajúci zložil skôr a výsledok prišiel ok neskôr, je to ENDED_EARLY. Ak prišiel timeout alebo nič, je to API_ERROR. Toto pravidlo je z poznámok v labeled_sample.jsonl.
3. Chyba resolve_address typu timeout/5xx je API_ERROR (nástroj zlyhal), no_match/ambiguous je ADDRESS_NOT_UNDERSTOOD. V noci 1 sa timeout resolvera nevyskytol.
4. Ak sa bot pokúsi o get_outage znova a uspeje, rozhoduje úspech (napravená chyba sa neráta).
5. 38 % = ended_by == bot / všetky hovory. Sedí presne (4 332 / 11 400), ale nemám dashboard, len calls.csv.
6. „Okno výpadku OMS“ = 20:40–21:30 UTC podľa oms_api_metrics.txt.
7. Neúspešné prepojenie počítam po ľuďoch cez caller_hash (226 ľudí, 12 sa neskôr dovolalo).
8. Kapacita operátorov: 3 × 60/4 = 45 hovorov/h, bez prestávok a bez dispečingu, ktorý rieši aj iné veci.
9. Že create_ticket timeouty súvisia s OMS, je odhad z časovej zhody (54 zo 60 v okne), nie overený fakt.


Čo by som robil s viac časom

1. Ručne olabelovať ďalších ~100 hovorov z menších skupín (ENDED_EARLY počas čakania, zlá adresa potvrdená „áno“) ako skutočný test set.
2. Zistiť, či volajúci niekedy potvrdil zlú adresu (resolver skracuje čísla domov). Taký hovor dnes vyzerá ako úspech, ale človek dostal info o cudzej adrese.
3. Overiť s Voltikou, prečo OMS vracia ETA v minulosti, a či create_ticket volá OMS.
4. Spočítať, koľko ľudí s neúspešným prepojením hlásilo skutočne nebezpečnú situáciu a čo sa s nimi stalo (incident report pre Voltiku).
5. Metrika na dashboard: podiel „vybavených“ podľa tohto evalu namiesto ended_by.

Čo som vedome nerobil

1. Žiadny ML ani LLM klasifikátor. Dáta sú štruktúrované a výsledok hovoru je v udalostiach (stav nástroja, prepojenie, zloženie). Pravidlá sú vysvetliteľné, deterministické a na workshope nepotrebujú sieť ani API kľúč. Pri LLM by som nevedel povedať, prečo sa na noci 2 zmenil label.
2. Nečítam text bota ani prepis volajúceho. Formulácie sa medzi nocami zmenia skôr ako štruktúra. Text bota som použil len raz, ako nezávislú kontrolu počtov, nie na rozhodovanie.
3. Nehľadal som hovory, kde volajúci potvrdil zlú adresu. Resolver niekedy skráti číslo domu (SNP 49 → SNP 4). Ak volajúci povie „áno“, hovor vyzerá ako úspech. Spoľahlivo sa to z dát rozoznať nedá a hádanie by pokazilo presnosť viac, než pomohlo. Je to v „Čo by som robil ďalej“.
4. 639 hovorov zložených na pozdrav nerátam ako zlyhanie bota. Nevieme, prečo zložili (omyl, dlhé čakanie, preferencia človeka). Pripísať ich botovi by bolo pohodlné pre klientku, ale nepoctivé.
5. Klientke som nesľúbil SMS ani termíny opráv. Bez potvrdenia od produktu a s 374 neaktuálnymi ETA by to bol sľub, ktorý nevieme dodržať. Namiesto termínu som sľúbil plán do štvrtka.
6. Nerobil som vlastný dashboard ani grafy. Zadanie ich nežiada a v time boxe bola dôležitejšia správnosť čísel a mail.
7. Pri create_ticket timeoutoch netvrdím, že príčinou je OMS. 54 zo 60 je v okne výpadku, ale je to len časová zhoda. V správe je to označené ako odhad.


Ako som použil AI nástroje

1. Delegoval som na Claude Code: profilovanie dát (typy udalostí, stavy, 37 vzorov hovorov), prvú verziu classify.py, drift testy, výpočty pre REPORT.md a návrh mailu.
2. Overil som sám: Kontrola 38%, prečítanie mailu, prehlad dat a vystup .py
3. Kde sa agent mýlil / kde som ho opravil: Oprava, ktorú vlastný klasifikátor nevedel zaradiť.
