function makeCOMPUSTATDerivedVariables(Params)
% PURPOSE: This function uses the stored variables from the COMPUSTAT annual and
% quarterly files to create additional variables that are used in the
% construction of some common anomalies
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCOMPUSTATDerivedVariables(Params)              % Creates additional variables
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeCOMPUSTATDerivedVariables(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

fprintf('\n\n\nNow working on making variables from Annual COMPUSTAT. Run started at %s.\n',char(datetime('now')));

load COGS
load XSGA
load DLC
load DLTT
OC = nanmatsum(COGS,XSGA);
D = nanmatsum(DLC,DLTT);
save Data/OC OC
save Data/D D
clear COGS XSGA DLC DLTT OC D

load PPEGT
load INVT
INV = nanmatsum(PPEGT,INVT); % (cummulative) "investment" (property plant and equipment + total inventories)
save Data/INV INV
clear PPEGT INVT INV

load NI
load DP
load WCAPCH
load CAPX
FCF = nanmatsum(NI,nanmatsum(DP,nanmatsum(-WCAPCH,-CAPX))); % free cash-flow (net earnings + depreciation and amortization - changes in working capital - capital expenditures)
save Data/FCF FCF
clear NI DP WCAPCH CAPX FCF

load PRSTKC
load PRSTKPC
load PRSTKCC
load DVC
temp = nanmatsum(PRSTKC,-PRSTKPC);
PRSTKCC(isnan(PRSTKCC)) = temp(isnan(PRSTKCC)); % stock repurchases (common stock only-- cash returned to share holders, like a dividend)
DIV = nanmatsum(DVC,PRSTKCC); % money returned to equity holders (dividends and buy-backs) 
save Data/DIV DIV
clear PRSTKC PRSTKPC PRSTKCC DVC DIV temp

load ACT
load LCT
WCAP = ACT - LCT;
save Data/WCAP WCAP
clear WCAP ACT LCT

load OANCF
load IB
load DP
load XIDO
load TXDC
load ESUBC
load SPPIV
load FOPO
load RECCH
load INVCH
load APALCH 
load TXACH 
load AOLOCH
temp = nanmatsum(IB,DP); % Income Before Extraordinary Items + Depreciation and Amortization
temp = nanmatsum(temp,XIDO); % + Extraordinary Items and Discontinued Operations
temp = nanmatsum(temp,TXDC); % + Deferred Taxes (CF)
temp = nanmatsum(temp,ESUBC); % + Equity in Net Loss (Earnings)
temp = nanmatsum(temp,-SPPIV); % - Sale of Property, Plant, and Equipment and Sale of Investments Gain (Loss)
temp = nanmatsum(temp,FOPO); % + Funds from Operations – Other
temp = nanmatsum(temp,RECCH); % + Accounts Receivable – Decrease (Increase)
temp = nanmatsum(temp,INVCH); % + Inventory – Decrease (Increase)
temp = nanmatsum(temp,APALCH); % + Accounts Payable and Accrued Liabilities – Increase (Decrease)
temp = nanmatsum(temp,TXACH); % + Income Taxes – Accrued – Increase (Decrease)
temp = nanmatsum(temp,AOLOCH); % + Assets and Liabilities – Other (Net Change)
CFO = temp; % Operating Activities – Net Cash Flow (i.e., CF from Ops)
CFO(isnan(CFO) == 1) = OANCF(isnan(CFO) == 1);
save Data/CFO CFO % CFO needed for Piotroski (this helps get better operating cash flows)
clear IB DP XIDO TXDC ESUBC SPPIV FOPO  RECCH INVCH APALCH TXACH AOLOCH CFO OANCF temp

load SEQ
load CEQ
load PSTK
load AT
load LT
SE = SEQ; % shareholder equity
temp = CEQ + PSTK;
SE(isnan(SE) == 1) = temp(isnan(SE) == 1); % uses common equity + preferred stock if SEQ is missing
temp = AT - LT;
SE(isnan(SE) == 1) = temp(isnan(SE) == 1); % uses assets - liabilities, if others are missing
clear SEQ CEQ PSTK AT LT temp

load PSTKRV
load PSTKL
load PSTK
PS = PSTKRV; % prefered stock
PS(isnan(PS) == 1) = PSTKL(isnan(PS) == 1);
PS(isnan(PS) == 1) = PSTK(isnan(PS) == 1);
clear PSTKRV PSTKL PSTK

load TXDITC
load TXDB
load ITCB
DT = TXDITC; % defered taxes
temp = nanmatsum(TXDB,ITCB);
DT(isnan(DT) == 1) = temp(isnan(DT) == 1);
clear TXDITC TXDB ITCB

BE = nanmatsum(SE,nanmatsum(DT,-PS)); % book equity is shareholder equity + deferred taxes - preferred stock

% add in the Davis, Fama and French (1997) book equities (from before the accounting data is available on Compustat)
load dates
load permno
if dates(1) <= 192612 % this only runs if your dates start December 1925
    load dff_be
    count_check = sum(sum(isfinite(dff_be)));
    count = 0;
    for i = 1:cols(dff_be)
        c = find(permno == dffpermno(i));
        for j = 1:rows(dff_be)
            if isfinite(dff_be(j,i)) == 1
                r = find(dates == 192506 + 100*j);
                BE(r,c) = dff_be(j,i);
                count = count + 1;
            end
        end
    end
end

% Following Fama-French (1993) we use book equity data for a given fiscal
% year starting at the end of June in the following calendar year, and we
% scale by market equity from the end of December of the preceeding year
% (this avoids a short momentum position from sneaking into value strategies)
load me
bm = BE./lag(me,6,nan); % I like to keep the negative BM firms, some don't

load SIC
FinFirms = (SIC >= 6000).*(SIC <= 6999);
% The assets of financial firms are very different (and larger than) those
% of other firms; when we scale by assets we'll often want to kick out financials

save Data/PS PS
save Data/BE BE
save Data/bm bm
save Data/FinFirms FinFirms
clear BE bm c count count_check dates dff_be dffpermno DT FinFirms i j me permno PS r SE SIC temp

% Replicate hml
load ret
load me
load bm
load dates
load NYSE
load ff
const = .01*ones(size(hml));

bm(bm < 0) = nan; % Fama and French kick out negative book-equity firms (the most growth-y
ind = makeBivSortInd(me,2,bm,[30 70],'breaksFilter',NYSE);      
[res,~] = runBivSort(ret,ind,2,3,dates,me,'printResults',0); % Carries over all {'Name','Value'} optional inputs from runUnivSort without 'addLongShort'

hmlrep = (res.pret(:,3)+res.pret(:,6)-res.pret(:,1)-res.pret(:,4))/2; % HML is made from the "corner" portfolios

% Should see a high (~99%) correlation, but it WON'T match perfectly, 
% for a couple of reasons. Fama-French construct the variable using data available at the time of construction 
% (they don't go back and change it if they fix data errors in crsp/compustat)
% It shouldn't matter: "value" is a robust phenomena-- one of the reasons it's important 
% is that the details don't "matter" for getting a real "exposure" to value

fprintf('Compare our HML with HML from Ken French''s website:\n');

index = isfinite(sum([hmlrep hml],2));
corrcoef([hmlrep(index) hml(index)]) % correlation shoud be >95%

prt(nanols(hml,[const])) % mean return to either factor should be ~0.38 %/mo.
prt(nanols(hmlrep,[const]))

prt(nanols(hml,[const hmlrep]))
prt(nanols(hmlrep,[const hml]))
clear ans bm cma const dates ff3 ff4 ff5 ff6 ffdates hml hmlrep ind ind_InX indBM3 index indME2 me mkt NYSE res res_inds ret rf rmw smb smb2 umd
fprintf('COMPUSTAT derived annual variables run ended at %s.\n', char(datetime('now')));

% Make quarterly book equity
load SEQQ
load CEQQ
load PSTKQ
load ATQ
load LTQ
SE = SEQQ; % shareholder equity
temp = CEQQ + PSTKQ;
SE(isnan(SE) == 1) = temp(isnan(SE) == 1); % uses common equity + preferred stock if SEQ is missing
temp = ATQ - LTQ;
SE(isnan(SE) == 1) = temp(isnan(SE) == 1); % uses assets - liabilities, if others are missing
clear SEQQ CEQQ PSTKQ ATQ LTQ

load PSTKQ
PS = PSTKQ; % prefered stock
clear PSTKQ

load TXDITCQ
DT = TXDITCQ; % defered taxes
clear TXDITCQ

BEQ = nanmatsum(SE,nanmatsum(DT,-PS)); % book equity is shareholder equity + deferred taxes - preferred stock
save data/BEQ BEQ
clear ans BEQ DT PS SE temp
% Make some additional variables

load REVTQ
load COGSQ
GPQ = REVTQ - COGSQ;
save data/GPQ GPQ
clear REVTQ COGSQ GPQ

load IBQ
load ATQ
roa = IBQ./lag(ATQ,3,nan);
save data/roa roa
clear ATQ IBQ roa

% SUE and dROE
load IBQ
load EPSPXQ
load beq
load dates

index = (IBQ ~= lag(IBQ,1,nan)).*isfinite(IBQ);
index(end-20:end,1:5)

BEQL0 = BEQ;
BEQL0(index == 0) = nan;
BEQL1 = nan(size(IBQ));
IBQL0 = IBQ;
IBQL0(index == 0) = nan;
IBQL4 = nan(size(IBQ));
EPSPXQL0 = EPSPXQ;
EPSPXQL0(index == 0) = nan;
EPSPXQL0(end-20:end,1:5)
EPSPXQL1 = nan(size(IBQ));
EPSPXQL2 = EPSPXQL1; EPSPXQL3 = EPSPXQL1; EPSPXQL4 = EPSPXQL1;
EPSPXQL5 = EPSPXQL1; EPSPXQL6 = EPSPXQL1; EPSPXQL7 = EPSPXQL1; EPSPXQL8 = EPSPXQL1;
EPSPXQL9 = EPSPXQL1; EPSPXQL10 = EPSPXQL1; EPSPXQL11 = EPSPXQL1; EPSPXQL12 = EPSPXQL1;

lind2 = index;

for i = 1:60
    lind2 = lind2 + index.*lag(index,i,0);
    lind = lind2.*lag(index,i,0);
    lIBQ = lag(IBQ,i,0);
    lBEQ = lag(BEQ,i,0);
    lEPSPXQ = lag(EPSPXQ,i,0);
    IBQL4(lind == 5) = lIBQ(lind == 5);
    BEQL1(lind == 2) = lBEQ(lind == 2);   
    EPSPXQL1(lind == 2) = lEPSPXQ(lind == 2);
    EPSPXQL2(lind == 3) = lEPSPXQ(lind == 3);
    EPSPXQL3(lind == 4) = lEPSPXQ(lind == 4);
    EPSPXQL4(lind == 5) = lEPSPXQ(lind == 5);
    EPSPXQL5(lind == 6) = lEPSPXQ(lind == 6);
    EPSPXQL6(lind == 7) = lEPSPXQ(lind == 7);
    EPSPXQL7(lind == 8) = lEPSPXQ(lind == 8);
    EPSPXQL8(lind == 9) = lEPSPXQ(lind == 9);
    EPSPXQL9(lind == 10) = lEPSPXQ(lind == 10);
    EPSPXQL10(lind == 11) = lEPSPXQ(lind == 11);
    EPSPXQL11(lind == 12) = lEPSPXQ(lind == 12);
    EPSPXQL12(lind == 13) = lEPSPXQ(lind == 13);
end

qmin = 6;
SUE = nan(size(IBQ));
dEPSvol = nan(size(IBQ));
dE2sigE = nan(size(IBQ));

for i = find(dates == 197101):rows(IBQ)
    temp = [EPSPXQL1(i,:)-EPSPXQL5(i,:);
        EPSPXQL2(i,:)-EPSPXQL6(i,:);
        EPSPXQL3(i,:)-EPSPXQL7(i,:);
        EPSPXQL4(i,:)-EPSPXQL8(i,:);
        EPSPXQL5(i,:)-EPSPXQL9(i,:);
        EPSPXQL6(i,:)-EPSPXQL10(i,:);
        EPSPXQL7(i,:)-EPSPXQL11(i,:);
        EPSPXQL8(i,:)-EPSPXQL12(i,:)];
    stemp = sum(isfinite(temp));
    temp = nanstd(temp);
    temp(stemp < qmin) = nan;
    dEPSvol(i,:) = temp;
    temp(temp == 0) = nan;
    SUE(i,:) = (EPSPXQL0(i,:)-EPSPXQL4(i,:))./temp;
end

SUERD = SUE;
SUE = FillMonths(SUE);
dROE = FillMonths((IBQL0 - IBQL4)./BEQL1);

save data/SUE SUE
save data/dROE dROE
clear ans BEQ BEQL0 BEQL1 dates dE2sigE dEPSvol dROE EPSPXQ EPSPXQL0 EPSPXQL1 ...
      EPSPXQL2 EPSPXQL3 EPSPXQL4 EPSPXQL5 EPSPXQL6 EPSPXQL7 EPSPXQL8 EPSPXQL9 ...
      EPSPXQL10 EPSPXQL11 EPSPXQL12 i IBQ IBQL0 IBQL4 index lBEQ lEPSPXQ lIBQ ...
      lind IBEQ lind2 qmin stemp SUE SUERD temp



% SUE2 -- simpler construction
% current earnings minus earnings from one year ago, scaled by the standard
% deviation of the last eight quarterly earnings
load dates
load IBQ
SUE2 = nan(size(IBQ));
for i = find(dates == 197101):rows(IBQ)
    SUE2(i,:) = (IBQ(i,:)-IBQ(i-12,:))./nanstd(IBQ(i-24:3:i-3,:));
end
save data/SUE2 SUE2

% dROA --
% difference between current earnings and average of the last four
% quarters, scaled by lagged assets
load ATQ
dROA = nan(size(IBQ));
for i = find(dates == 197101):rows(IBQ)
    dROA(i,:) = IBQ(i,:) - nanmean(IBQ(i-12:i-1,:));
end
dROA = dROA./ATQ;
save data/dROA dROA
clear IBQ ATQ dROA SUE2 i dates

% announcement month effect (Frazzini-Lamont)
load ret
load IBQ
load dates
load me

amonth = IBQ ~= lag(IBQ,1,nan);
amonth = isfinite(IBQ).*amonth;
% indAMO = isfinite(IBQ) + lag(amonth,2,nan); % firms that announced two months ago are 
                                         % likely to announce in the comming month
% res = runUnivSort(ret,indAMO,dates,me,'printResults',1,'plotFigure',0,'timePeriod',196306);
save data/amonth amonth
clear amonth ans dates IBQ indAMO me ret
