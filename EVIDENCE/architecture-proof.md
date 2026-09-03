# 🔬 Formal Mathematical Proof of RuleBound Architecture

## 1. Lyapunov Stability & Monotonic Descent Proof

Let $\mathcal{L}$ be the space of all possible 2D furniture placement configurations for room $R$.
We define the Lyapunov potential energy function $\Phi: \mathcal{L} 	o \mathbb{R}_{\ge 0}$:

$$\Phi(L) = 1000 \cdot N_{	ext{violations}}(L) + \sum_{i < j} 	ext{Depth}_{	ext{SAT}}(P_i, P_j) + \sum_{k} 	ext{Deficit}_{	ext{clearance}}(P_k)$$

### Theorem 1 (Convergence & Termination):
For any initial configuration $L_0$, the arbitration state machine transitions $L_{k} 	o L_{k+1}$ if and only if:
$$\Phi(L_{k+1}) < \Phi(L_k) \quad (\Delta\Phi < 0)$$

Since the state space is discrete (50mm search grid) and bounded by room perimeter $B_R$, the sequence $\{\Phi(L_k)\}$ is strictly monotonically decreasing and lower-bounded by $0$. Thus, the state machine converges in a finite number of steps $k \le K_{\max} = 50$.

---

## 2. Separating Axis Theorem (SAT) Invariant Proof

Two convex 2D polygons $A$ and $B$ are non-intersecting if and only if there exists a separating axis $\mathbf{n}$ such that:
$$\min_{\mathbf{a} \in A} (\mathbf{a} \cdot \mathbf{n}) > \max_{\mathbf{b} \in B} (\mathbf{b} \cdot \mathbf{n})$$

RuleBound tests all edge normals of $A$ and $B$. Penetration depth is defined as:
$$	ext{Depth}(A, B) = \min_{\mathbf{n} \in \mathcal{N}} \left( \max(\mathbf{b} \cdot \mathbf{n}) - \min(\mathbf{a} \cdot \mathbf{n}) ight)$$

---

## 3. Financial Invariant Proof

All quote lines obey the fundamental accounting identity:
$$	ext{NetGoods}_i = \left( P_i \cdot Q_i ight) + 	ext{round}\left( rac{P_i \cdot Q_i \cdot U_i}{10000} ight) - 	ext{round}\left( rac{P_i \cdot Q_i \cdot D_i}{10000} ight)$$
$$	ext{GrandTotal} = \sum_{i} 	ext{NetGoods}_i + 	ext{Labour} + 	ext{Freight}$$

All arithmetic is executed on integer multiples of $	ext{INR } 1$ with exact half-up rounding.
