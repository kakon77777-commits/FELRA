; A deliberately SATISFIABLE obligation, so the `refuted` path is exercised by a
; real solver rather than asserted to work. (a + b) - c is not zero in general.
(set-logic QF_LRA)
(declare-const a Real)
(declare-const b Real)
(declare-const c Real)
(assert (not (= (- (+ a b) c) 0.0)))
(check-sat)
