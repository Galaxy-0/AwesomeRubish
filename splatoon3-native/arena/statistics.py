"""Exact binomial confidence interval; draws stay separate from decided games."""
import math


def meets_a5_threshold(valid,void,parallel):
    """The revised A5 sample, void-rate and concurrent-room gate."""
    return (valid>=70 and parallel in (3,4) and
            void/(valid+void)<=.1)


def binomial_tail(n,k,p,upper):
    if p<=0:return float(0>=k) if upper else 1.
    if p>=1:return 1. if upper else float(n<=k)
    indices=range(k,n+1) if upper else range(k+1)
    return sum(math.exp(math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)+i*math.log(p)+(n-i)*math.log1p(-p)) for i in indices)


def exact_interval(wins,decided,confidence=.95):
    if type(wins) is not int or type(decided) is not int or not 0<=wins<=decided or not 0<confidence<1:raise ValueError('invalid binomial sample')
    if not decided:return (0.,1.)
    alpha=(1-confidence)/2
    def bound(upper):
        lo,hi=0.,1.
        for _ in range(64):
            mid=(lo+hi)/2
            value=binomial_tail(decided,wins,mid,upper)
            if (value<alpha if upper else value>alpha):lo=mid
            else:hi=mid
        return (lo+hi)/2
    return (0. if wins==0 else bound(True),1. if wins==decided else bound(False))


def summarize(outcomes):
    wins=outcomes.count('a');losses=outcomes.count('b');draws=outcomes.count('draw')
    if len(outcomes)!=wins+losses+draws:raise ValueError('unknown match outcome')
    low,high=exact_interval(wins,wins+losses)
    return dict(games=len(outcomes),wins=wins,losses=losses,draws=draws,
                win_rate=wins/len(outcomes) if outcomes else None,
                decided_win_rate=wins/(wins+losses) if wins+losses else None,
                decided_exact_95_interval=[low,high],stronger=low>.5,
                interval_method='Clopper-Pearson two-sided 95%; draws excluded from binomial trials')


def tournament_statistics(matches):
    valid=[m for m in matches if m.get('passed')]
    void=[m for m in matches if m.get('void')]
    result=summarize([m['outcome'] for m in valid])
    denominator=len(valid)+len(void)
    result.update(valid_games=len(valid),void_games=len(void),attempts=denominator,
                  void_rate=len(void)/denominator if denominator else 0.,
                  suspect_games=sum(bool(m.get('suspect')) for m in valid),
                  suspect_rate=sum(bool(m.get('suspect')) for m in valid)/len(valid) if valid else 0.,
                  void_reasons={reason:sum((m.get('void_reason') or 'unknown')==reason for m in void) for reason in sorted({m.get('void_reason') or 'unknown' for m in void})},
                  failed_or_cancelled=len(matches)-denominator)
    policies=[]
    for policy in (0,1):
        scores=[];enemy=own=enemy_env=own_env=0
        for m in valid:
            role=m['role_to_policy'].index(policy);hud=m['hud_by_role'][f'player_{role}']
            scores.append(m['score_by_role'][role])
            enemy+=hud['enemy_hud_downs'];own+=hud['own_hud_downs']
            enemy_env+=hud['enemy_environmental_downs'];own_env+=hud['own_environmental_downs']
        outcomes=[('draw' if m['outcome']=='draw' else 'a' if m['outcome']==('a' if policy==0 else 'b') else 'b') for m in valid]
        policies.append(dict(**summarize(outcomes),enemy_hud_downs=enemy,own_hud_downs=own,
            enemy_environmental_downs=enemy_env,own_environmental_downs=own_env,
            enemy_non_environment_classified_downs=enemy-enemy_env,
            score_percentage_points=dict(mean=sum(scores)/len(scores) if scores else None,min=min(scores) if scores else None,max=max(scores) if scores else None)))
    result['by_policy']=policies
    for key in ('wall_seconds','controlled_seconds'):
        times=[m[key] for m in valid if key in m]
        result[key]=dict(sum=sum(times),mean=sum(times)/len(times) if times else None,min=min(times) if times else None,max=max(times) if times else None)
    return result
