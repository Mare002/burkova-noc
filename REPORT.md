# Búrková noc: čísla, odpoveď klientke, čo ďalej

Všetky čísla sú z `predictions_night1.csv` (výstup `classify.py`), `calls.csv` a `oms_api_metrics.txt`. Časy sú miestne (UTC+1), ak nie je napísané inak.

## 2. Čísla

**38 %** je podiel hovorov s `ended_by = bot` (4 332 z 11 400). Meria, kto zložil, nie či hovor zlyhal: bot zloží aj po úspešnom hovore, keď oznámi poruchu a rozlúči sa. Takých je 3 028 zo 4 332. Klientka má pravdu, že ľudia odchádzali bez pomoci, ale nie v takom rozsahu.

**Výsledok:** vybavených 9 120 (80 %): 5 928 oznámená porucha, 2 052 hlásenie, 798 prepojenie, 342 odkázaných inam. **Bot nepomohol 1 368 (12 %).** 912 (8 %) zložilo samo, z toho 639 ešte pred zadaním adresy.

**Príčiny 1 368 zlyhaní:**

- 624 `get_outage` (OMS Voltiky): timeout 8 s alebo bez odpovede. 620 zo 684 API chýb padlo do okna 21:40–22:30, keď malo API 27–36 % chybovosť.
- 60 `create_ticket` (naše): timeout, 54 v tom istom okne.
- 456 adresa: 396× resolver nenašiel ani na 3. pokus, 60× vrátil zlú adresu (SNP 49 → SNP 4).
- 228 dispečing: 160× plný front (limit 10), 68× nikto nezdvihol. Sú to hlásenia spadnutého drôtu či iskrenia; z 226 ľudí sa neskôr dovolalo 12. Najvážnejšie zlyhanie noci.

**Mimo dashboardu:** 374 ľuďom bot povedal odhad obnovy, ktorý už uplynul (medián 43 min). Všetkých 2 112 hlásení má ako popis vetu bota, nie slová volajúceho. Ďalších 273 ľudí zložilo pri čakaní na pomalé OMS.

**Kto vlastní ktorú opravu**

| Oprava | Vlastník |
|---|---|
| Dashboard počíta „zložil bot“ ako zlyhanie, chýba metrika výsledku | Produktový tím (dashboard), na účte hneď vysvetlíme klientke |
| `description` v `create_ticket` = text bota | My na účte (konfigurácia flowu) |
| Kontrola ETA v minulosti pred prečítaním | My na účte (flow), zdroj chyby je OMS Voltiky |
| Fallback pri zlyhaní `get_outage`: založiť hlásenie namiesto „zavolajte neskôr“ | My na účte (flow); všeobecný fallback mechanizmus je produkt |
| Fallback pri neúspešnom prepojení nebezpečnej situácie (prioritné hlásenie + callback) | My na účte + Voltika (kto spracuje prioritné hlásenia) |
| Resolver: zlé čísla domov, skratky, ASR | Produktový tím |
| Timeouty `create_ticket` | Produktový tím / naša infra |
| Výpadok a latencia OMS API, staré ETA | Voltika IT |
| Front dispečingu (limit 10), počet nočných dispečerov | Voltika |

## 3. Odpoveď klientke

> **Predmet:** Nedeľná noc: čo sa stalo a čo s tým robíme
>
> Dobrý deň, pani Hudecová,
>
> prešiel som všetkých 11 400 hovorov z nedele.
>
> Číslo 38 % ukazuje, kto hovor ukončil, nie či zlyhal. Bot zloží aj po úspešnom hovore, keď oznámi poruchu a rozlúči sa. Takých bolo 3 028. Dashboard to zavádza a opravíme ho.
>
> Bot vybavil 9 120 hovorov (80 %). 1 368 ľuďom (12 %) nepomohol:
>
> - 624: medzi 21:40 a 22:30 neodpovedalo vaše API výpadkov,
> - 60: zlyhalo naše zakladanie hlásení,
> - 456: bot nenašiel adresu,
> - 228: hlásili nebezpečnú situáciu, ale dispečing bol plný alebo nezdvihol. Len 12 z nich sa dovolalo neskôr. Toto považujem za najvážnejšie.
>
> Našli sme aj dve vlastné chyby: 374 ľuďom bot povedal čas obnovy, ktorý už uplynul, a do hlásení sa neukladal popis od volajúceho.
>
> Pre porovnanie: traja noční operátori zvládnu asi 45 hovorov za hodinu, v špičke volalo 2 600.
>
> SMS od budúceho týždňa vám sľúbiť neviem. Kým bot hovorí neaktuálne časy, SMS by tú chybu len rozniesla. Do štvrtka vám pošlem plán opráv s termínmi vrátane SMS.
>
> Môžeme to zajtra prejsť po telefóne?
>
> S pozdravom

(~175 slov, bez predmetu a podpisu.)

## 4. Čo ďalej

1. **Tento týždeň, na účte:** nebezpečná situácia, ktorú sa nepodarí prepojiť, nesmie skončiť „zavolajte znova“. Bot založí prioritné hlásenie s adresou a číslom volajúceho a povie mu to. Pri zlyhaní `get_outage` rovnako: založiť hlásenie namiesto zloženia. Opraviť `description` a nečítať ETA, ktoré už uplynulo. Týka sa to až 912 z 1 368 zlyhaní (624 + 228 + 60).
2. **Dashboard:** namiesto `ended_by` ukazovať výsledok hovoru (tento eval), aby klientka nevidela 38 % ako zlyhanie.
3. **S Voltikou:** dohodnúť timeout/kapacitu OMS na búrky (alebo cache posledného stavu výpadkov) a čo robiť s frontom dispečingu (vyšší limit, záložné číslo, posily pri výstrahe SHMÚ).
4. **Produkt:** resolver (čísla domov, skratky „SNP“, výber obce), aby sme znížili 456 adresných zlyhaní.
5. **SMS:** nie od budúceho týždňa. Najskôr musí byť ETA spoľahlivé (374 neaktuálnych) a overiť súhlas so spracovaním čísla a SMS bránu. Navrhujem prvú verziu SMS len s číslom hlásenia, ETA až po oprave na strane OMS.

**Má Voltika bota vypnúť? Nie.** 3 operátori × (60 / 4 min) = 45 hovorov za hodinu. V špičke prišlo 2 600 za hodinu, za celú noc 11 400; operátori by zvládli ~270, teda 2,4 %. Bot vybavil 9 120. Zvyšných ~8 900 ľudí by bez bota počulo obsadzovací tón. Ale opravu dispečingového fallbacku (bod 1) treba spraviť pred ďalšou búrkou, nie po nej.
