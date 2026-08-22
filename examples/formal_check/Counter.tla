---------------- MODULE Counter ----------------
EXTENDS Naturals
VARIABLES n
vars == <<n>>
Limit == 8
Init == n = 0
Step == /\ n < Limit
        /\ n' = n + 1
Reset == /\ n = Limit
         /\ n' = 0
Next == Step \/ Reset
TypeOK == n \in 0..Limit
Bounded == n <= Limit
Spec == Init /\ [][Next]_vars
=============================================================================
