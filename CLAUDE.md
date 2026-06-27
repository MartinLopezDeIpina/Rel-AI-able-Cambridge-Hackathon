We are doing this challenge for a hackathon: 

## . Background

One of the most widely documented failures of large language models in legal practice is hallucination, the confident generation of fictitious case citations, statutes, and legal authorities. Lawyers, judges, and opposing counsel have already encountered AI-generated briefs citing cases that simply do not exist. In some instances, this has led to court sanctions and significant reputational damage for the lawyers involved. 

Legal professionals rely on cited authorities as the backbone of their arguments. A single fabricated or misapplied citation can undermine an entire submission, expose a client to adverse outcomes, and put a lawyer's practising certificate at risk. As AI tools become more deeply embedded in legal workflows, the risk of unchecked hallucinations appearing in high-stakes legal documents, contracts, briefs, court submissions, and regulatory filings, is growing rapidly. 

This challenge addresses that problem head-on: building a tool that catches what lawyers, and AI systems themselves, routinely miss. 

## 2. Challenge

Your mission is to build an LLM-powered solution that acts as a citation integrity layer for legal documents. Participants will build a tool that:   Scans legal text, including contracts, briefs, and memos, to identify all cited cases, statutes, and legal authorities   Extracts those citations and verifies whether they are real and correctly applied in context   Flags potentially dangerous or fabricated references before they cause harm to a client or practitioner   The tool should enable a user to upload or paste a legal document, receive a structured analysis of every citation within it, and understand, at a glance, which references are verified, which are suspect, and which do not exist at all. 

## 3. Scenario

You are assisting a partner at Alderton & Marsh LLP, a leading commercial litigation firm, in reviewing a skeleton argument prepared by a junior associate ahead of an urgent case management hearing in the High Court. The underlying dispute involves Crestholm Dynamics plc ("Crestholm"), a UK-based aerospace components manufacturer, and Veltros Industries Inc. ("Veltros"), a US-headquartered procurement conglomerate. Crestholm alleges that Veltros deliberately induced the breach of a long-term exclusive supply agreement between Crestholm and Airspan Aviation Group Ltd ("Airspan"), causing Crestholm to lose a contract worth approximately £47 million in projected revenues. 

The skeleton argument, which must be filed by 4:00 PM on the day of the hearing, advances Crestholm's position on three legal grounds:

1. Tortious interference with contractual relations;
2. The availability and quantum of expectation damages for lost future profits; and
3. The arguability of a without-notice injunction to prevent Veltros from entering into a substitute agreement with Airspan pending trial. 

In support of these three grounds, the junior associate has cited twelve cases, drawing on a combination of leading authorities and more recent High Court decisions. The associate used an AI drafting assistant to locate and summarise the relevant cases, working under significant time pressure. 

The partner reviewing the document has identified a concern: the associate has previously had difficulty accurately characterising older authorities, and the use of an AI drafting tool raises the additional risk that some of the cited cases may not exist at all, or may have been misrepresented in the argument. 

Your tool is given the skeleton argument. It must scan the document, extract all twelve citations, and return a clear, structured report indicating: 

1. Which cases exist and have been correctly applied in context; 
2. Which cases exist but have been mischaracterised or taken out of context; and 
3. Which cases do not appear to exist at all. 

The report must categorise each citation clearly, flag any material misrepresentation of a cited authority, and summarise in plain language what each case actually decided (where it exists). The partner must be able to act on the output immediately, without any legal database expertise. The output must be clear, actionable, and trustworthy. 

Focus only on the verification of the twelve case citations. Assume all other aspects of the skeleton argument are out of scope for this exercise


Our approach is: 
- extract the metadata from the citing document + the text on the citing document that supports the cite (reason for citation)
- convert the cases database resources to .txt frmo pdfs
- extract metadata from the resources
- Check whether the metadata is the same between citing and cited
- Do an argument verifier with probabilities to check whether the arguments are supported or not
- output a report and upload it to a frontend
