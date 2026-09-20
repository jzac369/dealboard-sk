# Chýbajúce Firestore indexy

Firestore vie zoraďovať a filtrovať naraz len vtedy, keď na tú kombináciu
existuje takzvaný composite index. Ak chýba, dotaz nevráti prázdny
výsledok — **zlyhá**, a stránka namiesto dealov ukáže „Žiadne dealy
nenájdené".

Preto na henkukaj.sk nefungovalo:

| Čo | Prečo |
|---|---|
| Ktorákoľvek kategória v hornej lište | chýbal index `category + status + zoradenie` |
| Triedenie **Najväčšia zľava** | chýbal index `status + discountPercent` |
| Pri kupónoch **Najpopulárnejšie** | chýbal index `status + votes` |

Fungovalo len „Najnovšie" a „Najhorúcejšie" bez kategórie, lebo tie dva
indexy Firestore vytvoril sám.

## Ako to opraviť

Klikni postupne na týchto päť odkazov. Každý otvorí Firebase konzolu s
predvyplneným indexom — stačí potvrdiť **Create index**.

1. [Dealy — Najväčšia zľava](https://console.firebase.google.com/v1/r/project/dealboard-e60bf/firestore/indexes?create_composite=Ck1wcm9qZWN0cy9kZWFsYm9hcmQtZTYwYmYvZGF0YWJhc2VzLyhkZWZhdWx0KS9jb2xsZWN0aW9uR3JvdXBzL2RlYWxzL2luZGV4ZXMvXxABGgoKBnN0YXR1cxABGhMKD2Rpc2NvdW50UGVyY2VudBACGgwKCF9fbmFtZV9fEAI)
2. [Dealy — kategória + Najnovšie](https://console.firebase.google.com/v1/r/project/dealboard-e60bf/firestore/indexes?create_composite=Ck1wcm9qZWN0cy9kZWFsYm9hcmQtZTYwYmYvZGF0YWJhc2VzLyhkZWZhdWx0KS9jb2xsZWN0aW9uR3JvdXBzL2RlYWxzL2luZGV4ZXMvXxABGgwKCGNhdGVnb3J5EAEaCgoGc3RhdHVzEAEaDQoJdGltZXN0YW1wEAIaDAoIX19uYW1lX18QAg)
3. [Dealy — kategória + Najhorúcejšie](https://console.firebase.google.com/v1/r/project/dealboard-e60bf/firestore/indexes?create_composite=Ck1wcm9qZWN0cy9kZWFsYm9hcmQtZTYwYmYvZGF0YWJhc2VzLyhkZWZhdWx0KS9jb2xsZWN0aW9uR3JvdXBzL2RlYWxzL2luZGV4ZXMvXxABGgwKCGNhdGVnb3J5EAEaCgoGc3RhdHVzEAEaCQoFdm90ZXMQAhoMCghfX25hbWVfXxAC)
4. [Dealy — kategória + Najväčšia zľava](https://console.firebase.google.com/v1/r/project/dealboard-e60bf/firestore/indexes?create_composite=Ck1wcm9qZWN0cy9kZWFsYm9hcmQtZTYwYmYvZGF0YWJhc2VzLyhkZWZhdWx0KS9jb2xsZWN0aW9uR3JvdXBzL2RlYWxzL2luZGV4ZXMvXxABGgwKCGNhdGVnb3J5EAEaCgoGc3RhdHVzEAEaEwoPZGlzY291bnRQZXJjZW50EAIaDAoIX19uYW1lX18QAg)
5. [Kupóny — Najpopulárnejšie](https://console.firebase.google.com/v1/r/project/dealboard-e60bf/firestore/indexes?create_composite=Ck9wcm9qZWN0cy9kZWFsYm9hcmQtZTYwYmYvZGF0YWJhc2VzLyhkZWZhdWx0KS9jb2xsZWN0aW9uR3JvdXBzL2NvdXBvbnMvaW5kZXhlcy9fEAEaCgoGc3RhdHVzEAEaCQoFdm90ZXMQAhoMCghfX25hbWVfXxAC)

Vytvorenie indexu chvíľu trvá (pri malej databáze zvyčajne do minúty).
V konzole má stav **Building**, potom **Enabled**. Až vtedy to funguje.

## Rovnaké indexy v súbore

`firestore.indexes.json` obsahuje to isté v strojovej podobe. Ak by si
niekedy používal Firebase CLI, nasadia sa príkazom:

```bash
firebase deploy --only firestore:indexes
```

Súbor je v repozitári hlavne preto, aby bolo zdokumentované, na čom
stránka stojí — keby sa index niekedy zmazal, je jasné, čo chýba.
