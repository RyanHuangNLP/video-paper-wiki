"""Deterministic ranking and gold evaluation over validated upstream hits."""
from __future__ import annotations
import copy,math
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
from typing import Any
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.evidence_join import validate_evidence_inventory,validate_evidence_mapping_authority

def _fail(message:str)->None: raise ContractError("RETRIEVAL_INVALID",message)
def validate_retrieval_config(value:object)->dict[str,Any]: return validate_document(value,"video-paper-wiki.retrieval-config.v1")
def validate_retrieval_policy(value:object)->dict[str,Any]: return validate_document(value,"video-paper-wiki.retrieval-policy.v1")

def derive_retrieval_config(policy:object,*,generation_sha256:object,mapping_sha256:object)->dict[str,Any]:
    try:
        if type(policy) is not dict or policy.get("schema")!="video-paper-wiki.retrieval-policy.v1":raise ValueError
        doc=validate_retrieval_policy(copy.deepcopy(policy))
        for value in (generation_sha256,mapping_sha256):
            if type(value) is not str or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):raise ValueError
        return copy.deepcopy(validate_retrieval_config({**doc,"schema":"video-paper-wiki.retrieval-config.v1",
            "generation_sha256":generation_sha256,"mapping_sha256":mapping_sha256}))
    except (ContractError,ValueError,TypeError) as exc:
        raise ContractError("CATALOG_STALE","retrieval policy or derived digest is invalid",{}) from exc

def _mapping(value:object,config:dict[str,Any])->tuple[dict[str,Any],dict[str,dict[str,Any]]]:
    value=validate_evidence_mapping_authority(value)
    if value["generation_sha256"]!=config["generation_sha256"] or value["mapping_sha256"]!=config["mapping_sha256"]:_fail("mapping or generation differs from retrieval policy")
    inventory=validate_evidence_inventory(value["inventory"]);units={x["evidence_unit_id"]:x for x in inventory["units"]};owners={x["paper_id"] for x in inventory["units"]}
    for item in value["chunks"]:
        if type(item) is not dict or set(item)!={"chunk_id","path","body_hash","page_body_hash","paper_id","evidence_unit_ids","default_evidence_unit_ids"}:_fail("mapping chunk shape differs")
        evidence=item["evidence_unit_ids"];default=item["default_evidence_unit_ids"];paper=item["paper_id"]
        if (type(evidence) is not list or type(default) is not list or evidence!=sorted(set(evidence)) or default!=sorted(set(default))
                or not set(default)<=set(evidence) or (paper is not None and paper not in owners)
                or any(unit not in units or units[unit]["paper_id"]!=paper for unit in evidence)
                or any(not units[unit]["default_eligible"] for unit in default)):_fail("mapping evidence ownership differs")
    mapped={x["chunk_id"]:x for x in value["chunks"]}
    if len(mapped)!=len(value["chunks"]):_fail("mapping chunk ids are duplicated")
    return inventory,mapped

def validate_retrieval_gold(value:object, inventory:object, config:object|None=None)->dict[str,Any]:
    doc=validate_document(value,"video-paper-wiki.retrieval-gold.v1"); inv=validate_evidence_inventory(inventory);cfg=validate_retrieval_config(config) if config is not None else None
    units={x["evidence_unit_id"]:x for x in inv["units"]}; gids=set()
    for row in doc["entries"]:
        if row["gold_id"] in gids:_fail("duplicate gold id")
        gids.add(row["gold_id"]); must=row["must_paper_ids"]; support=row["supporting_paper_ids"]
        if must!=sorted(must) or support!=sorted(support) or set(must)&set(support):_fail("paper truth sets differ")
        if row["variant_kind"] in {"named_title","topic_only"} and not 2<=len(must)<=3:_fail("comparison track requires two or three must papers")
        if row["variant_kind"] in {"exact_title_or_id","alias_or_semantic"} and len(must)!=1:_fail("single-paper track requires one must paper")
        if row["graded_relevance"]!={p:(2 if p in must else 1) for p in sorted(must+support)}:_fail("graded relevance differs")
        if cfg is not None and (row["corpus_version"]!=cfg["corpus_version"] or row["query_version"]!=cfg["query_version"]):_fail("gold version differs from retrieval config")
        eligible_papers={x["paper_id"] for x in inv["units"] if x["gold_eligible"]}
        if not set(must+support)<=eligible_papers:_fail("gold papers are not eligible inventory owners")
        counts={p:0 for p in must};unit_ids=[]
        for requested in row["required_evidence_units"]:
            actual=units.get(requested["evidence_unit_id"])
            if actual is None or not actual["gold_eligible"] or requested["paper_id"] not in must or any(actual[k]!=requested[k] for k in ("paper_id","claim_id","locator_fingerprint")):_fail("gold evidence does not bind eligible inventory")
            unit_ids.append(requested["evidence_unit_id"])
            if requested["paper_id"] in counts: counts[requested["paper_id"]]+=1
        if len(unit_ids)!=len(set(unit_ids)):_fail("gold evidence units are duplicated")
        if any(not 1<=n<=2 for n in counts.values()):_fail("must-paper evidence count differs")
    return doc

def rank_hits(hits:object, mapping:object, config:object)->dict[str,Any]:
    cfg=validate_retrieval_config(config)
    if type(hits) is not list:_fail("ranking inputs differ")
    if len(hits)>cfg["top_chunks"]:_fail("hit candidate depth exceeds config")
    _inventory,mapped=_mapping(mapping,cfg); rows=[];seen=set()
    for item in hits:
        if (type(item) is not dict or set(item)!={"chunk_id","score","path","body_hash","page_body_hash"} or type(item["chunk_id"]) is not str
                or type(item["score"]) not in (int,float) or not math.isfinite(item["score"]) or item["chunk_id"] in seen or item["chunk_id"] not in mapped):
            _fail("hit differs")
        seen.add(item["chunk_id"]); mapped_item=mapped[item["chunk_id"]]
        if any(item[key]!=mapped_item[key] for key in ("path","body_hash","page_body_hash")):_fail("hit does not bind exact mapped chunk")
        if mapped_item["paper_id"] is None:continue
        rows.append({**item,"paper_id":mapped_item["paper_id"],"evidence_unit_ids":mapped_item.get("default_evidence_unit_ids",mapped_item["evidence_unit_ids"])})
    rows.sort(key=lambda x:(-x["score"],x["paper_id"],x["chunk_id"]))
    best={}
    for row in rows: best.setdefault(row["paper_id"],row["score"])
    papers=[{"paper_id":p,"score":score} for p,score in sorted(best.items(),key=lambda x:(-x[1],x[0]))]
    top5={x["paper_id"] for x in papers[:5]}; candidates=[x for x in rows if x["paper_id"] in top5]
    chosen=[]; counts={}; used=set()
    # First ensure one highest chunk per paper, then fill in the same stable order.
    for phase in (0,1):
        for row in candidates:
            pid=row["paper_id"]
            if len(chosen)>=cfg["evidence_limit"]:break
            if phase==0 and counts.get(pid,0):continue
            if phase==1 and not counts.get(pid,0):continue
            if counts.get(pid,0)>=cfg["per_paper_evidence_limit"] or row["chunk_id"] in used:continue
            chosen.append(row);counts[pid]=counts.get(pid,0)+1;used.add(row["chunk_id"])
    return {"generation_sha256":mapping["generation_sha256"],"mapping_sha256":mapping["mapping_sha256"],"papers":papers[:cfg["top_papers"]],"top5":[x["paper_id"] for x in papers[:5]],"top10":[x["paper_id"] for x in papers[:10]],
            "evidence":[{"chunk_id":x["chunk_id"],"paper_id":x["paper_id"],"evidence_unit_ids":x["evidence_unit_ids"]} for x in chosen]}

def _bp(value:Fraction|Decimal)->int:
    with localcontext() as ctx:
        ctx.prec=40; d=Decimal(value.numerator)/Decimal(value.denominator) if isinstance(value,Fraction) else value
        return int((d*10000).quantize(Decimal(1),rounding=ROUND_HALF_UP))
def _ndcg(order:list[str], truth:dict[str,int])->Decimal:
    with localcontext() as ctx:
        ctx.prec=50
        def dcg(values): return sum((Decimal(2)**r-1)/(Decimal(i+2).ln()/Decimal(2).ln()) for i,r in enumerate(values[:5]))
        got=dcg([truth.get(x,0) for x in order]); ideal=dcg(sorted(truth.values(),reverse=True))
        if not ideal:_fail("graded truth is empty")
        return got/ideal

def evaluate_retrieval(*, gold:object, inventory:object, config:object, mapping:object, results:object)->dict[str,Any]:
    cfg=validate_retrieval_config(config);doc=validate_retrieval_gold(gold,inventory,cfg); inv=validate_evidence_inventory(inventory)
    known_papers={x["paper_id"] for x in inv["units"]}; known_units={x["evidence_unit_id"] for x in inv["units"]}
    mapped_inventory,mapped=_mapping(mapping,cfg)
    if mapped_inventory!=inv:_fail("evaluation mapping inventory differs")
    if type(results) is not dict or set(results)!={x["gold_id"] for x in doc["entries"]}:_fail("result set differs")
    rows=[]
    for truth in doc["entries"]:
        result=results[truth["gold_id"]]
        if type(result) is not dict or set(result)!={"generation_sha256","mapping_sha256","papers","top5","top10","evidence"} or result["generation_sha256"]!=cfg["generation_sha256"] or result["mapping_sha256"]!=cfg["mapping_sha256"]:_fail("rank result shape differs")
        papers=result["top10"]
        if result["top5"]!=papers[:5] or [x["paper_id"] for x in result["papers"]]!=papers:_fail("rank cutoffs differ")
        evidence=[]
        if type(result["evidence"]) is not list or len(result["evidence"])>8:_fail("rank evidence differs")
        for chunk in result["evidence"]:
            if type(chunk) is not dict or set(chunk)!={"chunk_id","paper_id","evidence_unit_ids"} or chunk["paper_id"] not in result["top5"]:_fail("rank evidence differs")
            source=mapped.get(chunk["chunk_id"])
            expected_units=source.get("default_evidence_unit_ids",source.get("evidence_unit_ids")) if source is not None else None
            if source is None or source.get("paper_id")!=chunk["paper_id"] or expected_units!=chunk["evidence_unit_ids"]:_fail("rank evidence is not derived from mapping")
            evidence.extend(chunk["evidence_unit_ids"])
        evidence=list(dict.fromkeys(evidence))
        if (len(papers)>10 or len(set(papers))!=len(papers) or not set(papers)<=known_papers or not set(evidence)<=known_units):_fail("result values differ")
        must=set(truth["must_paper_ids"]); required={x["evidence_unit_id"] for x in truth["required_evidence_units"]}
        rank=next((i+1 for i,p in enumerate(papers[:3]) if p in must),None)
        raw={"hit_at_3_bp":Fraction(1 if rank else 0),"mrr_at_3_bp":Fraction(1,rank) if rank else Fraction(0),
            "must_recall_at_10_bp":Fraction(len(must&set(papers[:10])),len(must)),"must_recall_at_5_bp":Fraction(len(must&set(papers[:5])),len(must)),
            "ndcg_at_5_bp":_ndcg(papers,truth["graded_relevance"]),"complete_at_5_bp":Fraction(1 if must<=set(papers[:5]) else 0),
            "evidence_recall_at_8_bp":Fraction(len(required&set(evidence)),len(required)),
            "evidence_complete_at_8_bp":Fraction(1 if all(any(x["paper_id"]==p and x["evidence_unit_id"] in set(evidence) for x in truth["required_evidence_units"]) for p in must) else 0)}
        rows.append({"gold_id":truth["gold_id"],"variant_kind":truth["variant_kind"],"metrics":{k:_bp(v) for k,v in raw.items()},"_raw":raw})
    macro={}; thresholds={
        "exact_title_or_id":{"hit_at_3_bp":10000,"mrr_at_3_bp":9000},
        "alias_or_semantic":{"hit_at_3_bp":10000,"mrr_at_3_bp":9000},
        "named_title":{"must_recall_at_10_bp":10000,"complete_at_5_bp":8000},
        "topic_only":{"must_recall_at_10_bp":10000,"must_recall_at_5_bp":9000,"ndcg_at_5_bp":8000,"complete_at_5_bp":8000,"evidence_recall_at_8_bp":8000,"evidence_complete_at_8_bp":8000}}
    if {x["variant_kind"] for x in rows}!=set(thresholds):_fail("all four retrieval tracks are required")
    for track in sorted(thresholds):
        selected=[x for x in rows if x["variant_kind"]==track]
        values={k:_bp(sum((x["_raw"][k] for x in selected),Fraction(0))/len(selected)) if isinstance(selected[0]["_raw"][k],Fraction)
                else _bp(sum((x["_raw"][k] for x in selected),Decimal(0))/Decimal(len(selected))) for k in thresholds[track]}
        macro[track]={"metrics":values,"thresholds":thresholds[track],"passed":all(values[k]>=v for k,v in thresholds[track].items())}
    for row in rows: row.pop("_raw")
    return {"queries":rows,"macro":macro,"passed":all(x["passed"] for x in macro.values())}
