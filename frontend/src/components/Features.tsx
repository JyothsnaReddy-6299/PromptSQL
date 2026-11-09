import { Brain, Database, Wand2, ShieldCheck, History, Sparkles } from "lucide-react";
import ScrollFloat from "./ScrollFloat";
import BentoCard from "./bento/BentoCard";
import NaturalLanguageSQLCard from "./bento/NaturalLanguageSQLCard";
import SchemaUnderstandingCard from "./bento/SchemaUnderstandingCard";
import DataCleaningCard from "./bento/DataCleaningCard";
import QueryValidationCard from "./bento/QueryValidationCard";
import QueryHistoryCard from "./bento/QueryHistoryCard";
import HowItWorks from "./HowItWorks";

export default function Features() {
  return (
    <>
      {/* ── Soft Pastel Bento Grid Features Section (#EDF3F5) ── */}
      <section id="features" className="py-16 sm:py-20 bg-gradient-to-b from-[#EAF2F5] via-[#EDF3F5] to-[#F5F1FA] relative overflow-hidden text-[#34434C]">
        {/* Soft atmospheric pastel radial glows */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/6 left-1/3 -translate-x-1/2 w-[650px] h-[450px] bg-[#70A9AA]/10 rounded-full blur-[140px]" />
          <div className="absolute top-1/2 right-1/10 w-[450px] h-[350px] bg-[#DCCEF2]/25 rounded-full blur-[150px]" />
          <div className="absolute bottom-1/6 left-1/10 w-[400px] h-[350px] bg-[#FCE9E3]/35 rounded-full blur-[140px]" />
        </div>

        {/* Faint decorative grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.035] pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(rgba(52,67,76,0.18) 1px, transparent 1px), linear-gradient(90deg, rgba(52,67,76,0.18) 1px, transparent 1px)`,
            backgroundSize: "64px 64px",
          }}
        />

        <div className="max-w-5xl lg:max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          {/* Section Introduction */}
          <ScrollFloat>
            <div className="text-center max-w-2xl mx-auto mb-10 sm:mb-12">
              {/* Eyebrow badge */}
              <div className="inline-flex items-center gap-2 bg-[#E1F0EF] border border-[#C2E4E2] px-3.5 py-1 rounded-full text-[#2B5758] text-[11px] font-semibold tracking-wider uppercase mb-3.5 shadow-2xs">
                <Sparkles size={12} className="text-[#70A9AA]" />
                <span>WHAT MAKES PROMPTSQL DIFFERENT</span>
              </div>

              {/* Main Heading */}
              <h2 className="text-2xl sm:text-3xl md:text-4xl font-extrabold tracking-tight text-[#34434C] leading-[1.15] mb-3">
                Everything you need to{" "}
                <span className="text-[#70A9AA] bg-gradient-to-r from-[#70A9AA] via-[#5BA0A2] to-[#458B8D] bg-clip-text text-transparent">
                  understand your data.
                </span>
              </h2>

              {/* Supporting Text */}
              <p className="text-sm sm:text-base text-[#687985] max-w-xl mx-auto leading-relaxed font-normal">
                From raw datasets to meaningful insights, explore a smarter way to work with your data.
              </p>
            </div>
          </ScrollFloat>

          {/* 5-Feature Balanced Bento Grid — Side-by-side from md: upwards */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4 lg:gap-5 items-stretch">
            {/* ── ROW 1: CARD 1 — Natural Language to SQL (~2/3 width, 7-8 cols) ── */}
            <div className="col-span-1 md:col-span-7 lg:col-span-8 flex flex-col">
              <ScrollFloat delay={40}>
                <BentoCard
                  accentColor="teal"
                  badge="Core Engine"
                  title="Natural Language to SQL"
                  description="Ask questions in plain English and let AI translate them into optimized, production-grade SQL queries."
                  icon={<Brain size={18} />}
                  className="h-full"
                >
                  <NaturalLanguageSQLCard />
                </BentoCard>
              </ScrollFloat>
            </div>

            {/* ── ROW 1: CARD 2 — Intelligent Schema Understanding (~1/3 width, 4-5 cols) ── */}
            <div className="col-span-1 md:col-span-5 lg:col-span-4 flex flex-col">
              <ScrollFloat delay={100}>
                <BentoCard
                  accentColor="blue"
                  badge="Relational Mapping"
                  title="Intelligent Schema Understanding"
                  description="Automatically understand your dataset structure, column data types, and primary keys."
                  icon={<Database size={18} />}
                  className="h-full"
                >
                  <SchemaUnderstandingCard />
                </BentoCard>
              </ScrollFloat>
            </div>

            {/* ── ROW 2: CARD 3 — AI-Powered Data Cleaning (1/2 width, 6 cols) ── */}
            <div className="col-span-1 md:col-span-6 lg:col-span-6 flex flex-col">
              <ScrollFloat delay={160}>
                <BentoCard
                  accentColor="peach"
                  badge="Quality Suite"
                  title="AI-Powered Data Cleaning"
                  description="Identify missing values, duplicate records, and inconsistent data formats before analysis."
                  icon={<Wand2 size={18} />}
                  className="h-full"
                >
                  <DataCleaningCard />
                </BentoCard>
              </ScrollFloat>
            </div>

            {/* ── ROW 2: CARD 4 — Query Validation and Safe Execution (1/2 width, 6 cols) ── */}
            <div className="col-span-1 md:col-span-6 lg:col-span-6 flex flex-col">
              <ScrollFloat delay={220}>
                <BentoCard
                  accentColor="lavender"
                  badge="Safety Guardrails"
                  title="Query Validation and Safe Execution"
                  description="Validate generated SQL before execution and handle invalid queries gracefully with read-only sandbox constraints."
                  icon={<ShieldCheck size={18} />}
                  className="h-full"
                >
                  <QueryValidationCard />
                </BentoCard>
              </ScrollFloat>
            </div>

            {/* ── ROW 3: CARD 5 — Query History and Export (Full width, 12 cols) ── */}
            <div className="col-span-1 md:col-span-12 lg:col-span-12 flex flex-col">
              <ScrollFloat delay={280}>
                <BentoCard
                  accentColor="slate"
                  badge="Audit & Reporting"
                  title="Query History and Export"
                  description="Revisit previous analyses, verify execution runtimes, and export useful results for reporting in clean CSV or PDF formats."
                  icon={<History size={18} />}
                  className="h-full"
                >
                  <QueryHistoryCard />
                </BentoCard>
              </ScrollFloat>
            </div>
          </div>
        </div>
      </section>

      {/* ── Horizontal Process Timeline How It Works Section ── */}
      <HowItWorks />
    </>
  );
}
