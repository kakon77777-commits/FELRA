; The same fact examples/cross_backend measures in exact rational arithmetic,
; here as a proof obligation in real arithmetic.
;
; cross_backend evaluates (a + b) - c in float64 / Decimal / Rational and reports
; that float64 disagrees. This asks z3 whether the identity holds in the reals at
; all — a different question, answered by a different instrument. The negation is
; asserted, so `unsat` means the identity is a theorem.
(set-logic QF_LRA)
(declare-const a Real)
(declare-const b Real)
(declare-const c Real)
(assert (= a (/ 1.0 10.0)))
(assert (= b (/ 2.0 10.0)))
(assert (= c (/ 3.0 10.0)))
(assert (not (= (- (+ a b) c) 0.0)))
(check-sat)
