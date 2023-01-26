function makeNovyMarxVelikovAnomalies(Params)
% PURPOSE: This function creates the 23 signals used in Novy-Marx and
% Velikov (RFS, 2016)
%------------------------------------------------------------------------------------------
% USAGE:   
% makeNovyMarxVelikovAnomalies(Params)              % Creates anomaly signals
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
% makeNovyMarxVelikovAnomalies(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2016, A taxonomy of anomalies and their
%  trading costs, Review of Financial Studies, 29 (1): 104-147
%  2. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on making anomaly signals from Novy-Marx and Velikov (RFS, 2016). Run started at %s.\n', char(datetime('now')));

% Load a few basic variables 
load ret
load me
load dates


% Store a few constants
nMonths = size(ret, 1);
nStocks = size(ret, 2);

% Store the anomaly 3-d array
anoms=nan(nMonths, nStocks, 23);

% Size
juneIndicator = dates - 100*floor(dates/100) == 6;
screen = repmat(juneIndicator, 1, nStocks); 
Size = -me.*screen;
Size(Size == 0) = nan;
anoms(:,:,1) = Size;
labels(1) = {'size'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Value
load bm
value = bm;
anoms(:,:,2) = value;
labels(2) = {'value'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

%  Profitability
load GP
load AT
load FinFirms
gp = GP./AT; 
gp(FinFirms == 1) = nan; 
anoms(:,:,3) = gp;
labels(3) = {'grossProfitability'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% ValProf
load GP
load AT
load FinFirms
load bm
gp = GP./AT; 
gp(FinFirms == 1) = nan; 
bm(bm==0) = nan;
rank2 = tiedrank(gp')';
rank3 = tiedrank(bm')';
valProf = rank2 + rank3;
anoms(:,:,4) = valProf;
labels(4) = {'valProf'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Accruals
load AT
load ACT
load CHE
load LCT
load TXP
load DP
load DLC
dCA   = ACT - lag(ACT, 12, nan);
dCash = CHE - lag(CHE, 12, nan);
dCL   = LCT - lag(LCT, 12, nan);
dSTD  = DLC - lag(DLC, 12, nan);
dTP   = TXP - lag(TXP, 12, nan);
Dep = DP;
Accruals = (dCA - dCash) - (dCL - dSTD - dTP) - Dep;
accruals = - 2*Accruals ./ (AT + lag(AT, 12, nan));
anoms(:,:,5) = accruals;
labels(5) = {'accruals'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Asset growth
load AT
load FinFirms
assetGrowth = -AT./lag(AT,12,nan);
assetGrowth(FinFirms==1) = nan;
anoms(:,:,6) = assetGrowth;
labels(6) = {'assetGrowth'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Investment
load PPEGT
load INVT
load AT
load FinFirms
AT(FinFirms==1) = nan;
investment = -( PPEGT - lag(PPEGT,12,nan) + ... 
                 INVT - lag(INVT,12,nan) ) ./ lag(AT, 12, nan);
anoms(:,:,7) = investment;
labels(7) = {'investment'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Piotroski's F-score (JAR 2000)
%  9 "Financial Performance" indicators
%       4 "profitability," 3 "leverage/liquidity," and 2 "efficiency"
load bm
load BE
load CFO
load IB
load AT
load DLTT
load ACT
load LCT
load SCSTKC
load PRSTKCC
load REVT
load COGS
load shrout
load ADJEX
I = sum(isfinite(bm),2) > 0;
b = min(find((sum(isfinite(bm),2)>0)==1));
ROA = IB./lag(AT,12,nan);           % return-on-assets -- Piotroski uses this
DTA = DLTT./AT;                     % long-term debt-to-assets
ATL = ACT./LCT;                     % current assets-to-current liabilities
EqIss = nanmatsum(SCSTKC,-PRSTKCC); % note: most firms don't report anything here
dshrout = shrout./lag(shrout,12,nan)-1;
GM = 1 - COGS./REVT;                % gross margins
ATO = REVT./lag(AT,12,nan);         % assets turnover
% alternative EqIss
temp2 = shrout./ADJEX;
temp2 = log(temp2./lag(temp2,12,nan));
EqIss = nan(size(EqIss)); EqIss(b:12:end,:) = temp2(b:12:end,:);
clear BE AT ACT LCT SCSTKC PRSTKCC REVT COGS shrout ADJEX I b
% Financial Performance Signals: Profitability.
F_ROA = (IB > 0)*1; 
F_CFO = (CFO > 0)*1; 
F_DROA = (ROA - lag(ROA,12,nan) > 0)*1; 
F_ACCR = (CFO - IB > 0)*1; 
% Financial Performance Signals: Leverage, Liquidity, and Source of Funds
F_DLEV = ((DTA - lag(DTA,12,nan) < 0) + (DLTT == 0).*(lag(DLTT,12,nan) == 0) > 0)*1; 
F_ATL = (ATL - lag(ATL,12,nan) > 0)*1; 
F_EQ = (EqIss <= 0)*1; 
% Financial Performance Signals: Operating Efficiency.
F_GM = (GM - lag(GM,12,nan) > 0)*1; 
F_ATO = (ATO - lag(ATO,12,nan) > 0)*1; 
% available signals
a1 = isfinite(IB); 
a2 = isfinite(CFO); 
a3 = isfinite(ROA - lag(ROA,12,nan)); 
a4 = isfinite(CFO - IB); 
a5 = isfinite(DTA - lag(DTA,12,nan));
a6 = isfinite(ATL - lag(ATL,12,nan));
a7 = isfinite(EqIss); 
a8 = isfinite(GM - lag(GM,12,nan)); 
a9 = isfinite(ATO - lag(ATO,12,nan)); 
clear IB CFO ROA DTA ATL EqIss GM ATO DLTT dshrout
piotroski = F_ROA + F_CFO + F_DROA + F_ACCR + F_DLEV + F_ATL + F_EQ + F_GM + F_ATO;
clear F_ROA F_CFO F_DROA F_ACCR F_DLEV F_ATL F_EQ F_GM F_ATO
available = a1 + a2 + a3 + a4 + a5 + a6 + a7 + a8 + a9;
clear a1 a2 a3 a4 a5 a6 a7 a8 a9;
temp = piotroski;
temp(available < 9) = nan;
piotroski = temp+tiedrank(bm)/1000;
anoms(:,:,8) = piotroski;
labels(8) = {'piotroski'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Issuance
load dashrout
screen = ones(size(ret));
issuance = -dashrout.*screen;
anoms(:,:,9) = issuance;
labels(9) = {'issuance'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Return on book equity
load IBQ
load BEQ
roe = IBQ./lag(BEQ,3,nan);
anoms(:,:,10) = roe;
labels(10) = {'roe'};
clearvars -except Params anoms ret me dates labels nMonths nStocks



% Distress risk
load IVOL
load prc
load ff
load ACTQ
load ATQ
load CHEQ
load DLCQ
load DLTTQ
load IBQ
load LCTQ
load LTQ
load NIQ
load PIQ
mktmat = repmat(mkt+rf,1,cols(me));
temp = nansum(me')';
memat = repmat(temp,1,cols(me));
coef = [-20.264;
         1.416;
        -7.129;
         1.411;
        -0.045;
        -2.132;
         0.075;
        -0.058];
c = 2^(-1/3);
NIfac = (1-c^3)/(1-c^12);
NIMTAAVG = nan(size(me));
niq = NIQ./(LTQ+me);
for i = 10:rows(me)
    NIMTAAVG(i,:) = NIfac*(niq(i,:)+(c^3)*niq(i-3,:)+(c^6)*niq(i-6,:)+(c^9)*niq(i-9,:));
end
TLMTA = LTQ./(LTQ+me);
EXRET = log(1+ret)-log(1+mktmat);
XRfac = (1-c)/(1-c^12);
EXRETAVG = nan(size(me));
for i = 13:size(me, 1)
    temp = EXRET(i-1,:);
    for j = 2:12
        temp = temp + (c^j)*EXRET(i-j,:);
    end
    EXRETAVG(i,:) = XRfac*temp;
end
SIGMA = sqrt(252)*IVOL;
RSIZE = log(me./memat);
CASHMTA = CHEQ./(LTQ+me);
load BE
sum(sum(BE < 0));
adjBE = 0.9*BE + 0.1*me;
adjBE(adjBE <= 0) = 0.001;
MB = lag(me,6,nan)./adjBE;
index = find(sum(isfinite(MB),2)>0);
for i = index'
    for j = 1:11
        if i+j <= rows(ret)
            MB(i+j,:) = MB(i,:);
        end
    end
end
PRICE = min(abs(prc),15*ones(size(prc)));
PRICE(PRICE < 1) = nan;
PRICE(isnan(prc)) = nan;
% DISTRESS = coef(1)*NIMTAAVG + coef(2)*TLMTA + coef(3)*EXRETAVG + coef(4)*SIGMA + coef(5)*RSIZE + coef(6)*CASHMTA + coef(7)*MB + coef(8)*PRICE;
DISTRESS = coef(1)*winsorize(NIMTAAVG,5);
DISTRESS = DISTRESS + coef(2)*winsorize(TLMTA,5);
DISTRESS = DISTRESS + coef(3)*winsorize(EXRETAVG,5);
DISTRESS = DISTRESS + coef(4)*winsorize(SIGMA,5);
DISTRESS = DISTRESS + coef(5)*winsorize(RSIZE,5);
DISTRESS = DISTRESS + coef(6)*winsorize(CASHMTA,5);
DISTRESS = DISTRESS + coef(7)*winsorize(MB,5);
DISTRESS = DISTRESS + coef(8)*winsorize(PRICE,5);
distress = -DISTRESS;
anoms(:,:,11) = distress;
labels(11) = {'distress'};
clearvars -except Params anoms ret me dates labels nMonths nStocks



% ValMom & ValMomPRof
load R
load GP
load AT
load FinFirms
load bm
gp = GP./AT; % this is profitability (gross profits / asset)
gp(FinFirms == 1) = nan; % and we drop financials, because this ratio doesn't mean much for them
bm(bm==0) = nan;
rank1 = tiedrank(R')';
rank2 = tiedrank(gp')';
rank3 = tiedrank(bm')';
valMom = rank1 + FillMonths(rank3);
valMomProf = rank1 + FillMonths(rank2) + FillMonths(rank3);
anoms(:,:,12) = valMomProf;
labels(12) = {'valMomProf'};
anoms(:,:,13) = valMom;
labels(13) = {'valMom'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Idiosyncratic Volatility
load IffVOL3
idiosyncraticVolatility = -IffVOL3;
anoms(:,:,14) = idiosyncraticVolatility;
labels(14) = {'idiosyncraticVolatility'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Momentum
momentum = makePastPerformance(ret,12,1); 
anoms(:,:,15) = momentum;
labels(15) = {'momentum'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% PEAD (SUE)
load SUE2
peadSUE = SUE2;
anoms(:,:,16) = peadSUE;
labels(16) = {'peadSUE'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% PEAD (CAR3)
load CAR3
peadCAR3 = CAR3;
anoms(:,:,17) = peadCAR3;
labels(17) = {'peadCAR3'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Industry momentum
load FF49
load iret
load ireta
industryMomentum = assignToPtf(ireta,sort(iret,2)); 
industryMomentum(industryMomentum == 0) = nan; 
industryMomentum = industryMomentum./repmat(max(industryMomentum')',1,size(ret,2));
anoms(:,:,18) = industryMomentum;
labels(18) = {'industryMomentum'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Industry-Relative Reversals
load FF49
load ireta
IRR = tiedrank(ireta'-ret')'; 
industryRelativeReversal = IRR./repmat(max(IRR')',1,cols(ret));
anoms(:,:,19) = industryRelativeReversal;
labels(19) = {'industryRelativeReversal'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% High freq Combo
load iret
load ireta
IRR = tiedrank(ireta'-ret')'; 
IRR = IRR./repmat(max(IRR')',1,cols(ret));
IMOM = assignToPtf(ireta,sort(iret,2)); 
IMOM(IMOM == 0) = nan; 
IMOM = IMOM./repmat(max(IMOM')',1,size(ret,2));
highFrequencyCombo = IRR + IMOM;
anoms(:,:,20) = highFrequencyCombo;
labels(20) = {'highFrequencyCombo'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Reversals
reversals = -ret;
anoms(:,:,21) = reversals;
labels(21) = {'reversals'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% Seasonality (Heston-Sadka)
seasonality = zeros(size(ret));
for i =1:5
   seasonality = seasonality + lag(ret, 12*i -1, nan);
end
seasonality(seasonality==0) = nan;
anoms(:,:,22) = seasonality;
labels(22) = {'seasonality'};
clearvars -except Params anoms ret me dates labels nMonths nStocks


% IRRLowVOl
load IVOL
load ireta
load NYSE
ind = makeUnivSortInd(IVOL,2,NYSE);
IRR = tiedrank(ireta'-ret')'; 
IRR = IRR./repmat(max(IRR')',1,cols(ret));
industryRelativeReversalLowVol = IRR;
industryRelativeReversalLowVol(ind==2) = nan;
anoms(:,:,23) = industryRelativeReversalLowVol;
labels(23) = {'industryRelativeReversalLowVol'};
clearvars -except Params anoms ret me dates labels nMonths nStocks

% Stack all the matrices into a table
load permno
nObs = nStocks * nMonths;
nAnoms = size(anoms,3);

% Start with the permno & month columns
outputData=[reshape(repmat(permno', nMonths, 1      ), nObs, 1) ...
            reshape(repmat(dates  , 1      , nStocks), nObs, 1)];

% Append all the anomaly columns
for i=1:nAnoms
    outputData=[outputData reshape(anoms(:,:,i), nObs, 1)];
end

% Remove rows with NaNs for all 23 anomalies
outputData(sum(isfinite(outputData),2)==2,:) = [];

% Convert to a table & change variable names
outputData = array2table(outputData);
outputData.Properties.VariableNames = [{'permno','dates'},labels];

% Store the general data path
dataPath = [Params.directory, 'Data/'];

% Check if the Data/Anomalies directory exists
if ~exist([dataPath,'Anomalies'], 'dir')
    mkdir([dataPath,'Anomalies'])
end
addpath(genpath(pwd));

% Output the data to a .csv
fileName = [dataPath,'Anomalies/novyMarxVelikovAnomalies.csv'];
writetable(outputData, fileName);

% Timekeeping
fprintf('Run ended, anomaly signal data exported at %s.\n', char(datetime('now')));
