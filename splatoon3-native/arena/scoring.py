"""Observer-local Turf scores reconciled by the agreed winner rule."""
import math

SCORING_RULE='peer-winner-average-v1'


def compare_scores(observer0,observer1,roles):
    if sorted(roles)!=[0,1]:raise ValueError('invalid policy roles')
    raw=[[float(v) for v in values] for values in (observer0,observer1)]
    if any(len(values)!=2 or any(not math.isfinite(v) or not 0<=v<=100 for v in values) for values in raw):
        raise ValueError('invalid native Turf scores')
    aligned=[raw[0],raw[1][::-1]]
    def winner(values):
        return None if abs(values[0]-values[1])<1e-6 else int(values[1]>values[0])
    winners=[winner(v) for v in aligned]
    delta=[aligned[0][n]-aligned[1][n] for n in (0,1)]
    average=[(aligned[0][n]+aligned[1][n])/2 for n in (0,1)]
    void=winners[0]!=winners[1]
    outcome=None if void else 'draw' if winners[0] is None else 'a' if roles[winners[0]]==0 else 'b'
    return dict(scoring_rule=SCORING_RULE,score_peers_native_order=raw,
                score_peers_by_role=aligned,score_difference_by_role=delta,
                score_max_difference_pp=max(abs(v) for v in delta),
                score_by_role=average,turf_ratio_by_role=[v/100 for v in average],
                winner_by_observer=winners,suspect=max(abs(v) for v in delta)>2.,
                void=void,void_reason='peer_winner_disagreement' if void else None,outcome=outcome)
