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
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on making variables derived from COMPUSTAT. Run started at %s.\n',char(datetime('now')));

% Store the general data path
dataPath = [Params.directory, 'Data/'];

% Make Operating costs 
load COGS
load XSGA
OC = nanmatsum(COGS, XSGA);
save([dataPath,'OC.mat'],'OC');
clearvars -except dataPath Params

% Make Total Debt
load DLC
load DLTT
D = nanmatsum(DLC, DLTT);
save([dataPath,'D.mat'],'D');
clearvars -except dataPath Params

% Make Investment. (Cummulative) Investment = property plant and equipment
% + total inventories
load PPEGT
load INVT
INV = nanmatsum(PPEGT, INVT); 
save([dataPath,'INV.mat'],'INV');
clearvars -except dataPath Params

% Make free cash-flow = net earnings + depreciation and amortization -
% changes in working capital - capital expenditures)
load NI
load DP
load WCAPCH
load CAPX
FCF = nanmatsum(NI, nanmatsum(DP, nanmatsum(-WCAPCH,-CAPX))); 
save([dataPath,'FCF.mat'],'FCF');
clearvars -except dataPath Params

% Make dividends (reall it's money returned to equity holders (dividends 
% and buy-backs) 
load PRSTKC
load PRSTKPC
load PRSTKCC
load DVC
temp = nanmatsum(PRSTKC, -PRSTKPC);
PRSTKCC(isnan(PRSTKCC)) = temp(isnan(PRSTKCC)); 
DIV = nanmatsum(DVC,PRSTKCC); 
save([dataPath, 'DIV.mat'],'DIV');
clearvars -except dataPath Params

% Make working capital
load ACT
load LCT
WCAP = ACT - LCT;
save([dataPath, 'WCAP.mat'],'WCAP');
clearvars -except dataPath Params

% Make CFO (cash flow from operations)
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
temp = nanmatsum(IB, DP);       % Income Before Extraordinary Items + Depreciation and Amortization
temp = nanmatsum(temp, XIDO);   % + Extraordinary Items and Discontinued Operations
temp = nanmatsum(temp, TXDC);   % + Deferred Taxes (CF)
temp = nanmatsum(temp, ESUBC);  % + Equity in Net Loss (Earnings)
temp = nanmatsum(temp, -SPPIV); % - Sale of Property, Plant, and Equipment and Sale of Investments Gain (Loss)
temp = nanmatsum(temp, FOPO);   % + Funds from Operations – Other
temp = nanmatsum(temp, RECCH);  % + Accounts Receivable – Decrease (Increase)
temp = nanmatsum(temp, INVCH);  % + Inventory – Decrease (Increase)
temp = nanmatsum(temp, APALCH); % + Accounts Payable and Accrued Liabilities – Increase (Decrease)
temp = nanmatsum(temp, TXACH);  % + Income Taxes – Accrued – Increase (Decrease)
temp = nanmatsum(temp, AOLOCH); % + Assets and Liabilities – Other (Net Change)
CFO = temp;                     % Operating Activities – Net Cash Flow (i.e., CF from Ops)
CFO(isnan(CFO)) = OANCF(isnan(CFO));
save([dataPath, 'CFO.mat'],'CFO');
clearvars -except dataPath Params

% Make book equity. Start with shareholder's equity
load SEQ
load CEQ
load PSTK
load AT
load LT
SE = SEQ;                                  % Shareholder equity
temp = CEQ + PSTK;
SE(isnan(SE)) = temp(isnan(SE));           % Uses common equity + preferred stock if SEQ is missing
temp = AT - LT;
SE(isnan(SE)) = temp(isnan(SE));           % Uses assets - liabilities, if others are missing

% Make preferred stock
load PSTKRV
load PSTKL
load PSTK
PS = PSTKRV; 
PS(isnan(PS)) = PSTKL(isnan(PS));
PS(isnan(PS)) = PSTK(isnan(PS));

% Make Deferred taxes
load TXDITC
load TXDB
load ITCB
DT = TXDITC; 
temp = nanmatsum(TXDB,ITCB);
DT(isnan(DT)) = temp(isnan(DT));

% Book equity is shareholder equity + deferred taxes - preferred stock
BE = nanmatsum(SE,nanmatsum(DT,-PS)); 

% Add in the Davis, Fama and French (1997) book equities (from before the
% accounting data is available on Compustat)
% First load the dates and permno vectors
load dates
load permno

% Unzip and read the FF historical book equity file. Data is organized as:
% permno start_year end_year BE_1926 BE_1927 .... BE_2001
ffURL    = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Historical_BE_Data.zip';
ffHistBE = unzip(ffURL,[dataPath,'FF']);
opts     = detectImportOptions(char(ffHistBE));
ffData   = readtable(char(ffHistBE),opts);

% Turn it into an array
ffData = table2array(ffData);

% Store the permnos & remove the dates
ffPermno = ffData(:,1);
ffData(:,1:3)=[];

% Remove NaNs (FF use -99.99 for those) and rearrange
indIsNan = (ffData == -99.99);
ffData(indIsNan) = nan;

% Create the FF dates mapping
ffDates    = (100 * (1926:2001) + 6)';

% Drop the years not in our sample
colsToDrop = ~ismember(ffDates, dates);
ffData(:, colsToDrop) = [];
ffDates(colsToDrop) = [];

% Store the dimensions of the FF data
nYears = length(ffDates);
nPermnos = size(ffData,1);

if nYears > 0
    % Loop through the rows (i.e., permnos) and assign the available BEs    
    for i = 1:nPermnos
        indBE = find(isfinite(ffData(i, :)));
        if ~isempty(indBE)
            rowsInd = (ismember(dates, ffDates(indBE)));
            c = find(permno==ffPermno(i));
            if ~isempty(c)
                BE(rowsInd, c) = ffData(i, indBE)';
            end    
        end
    end
end

% Following Fama-French (1993) we use book equity data for a given fiscal
% year starting at the end of June in the following calendar year, and we
% scale by market equity from the end of December of the preceeding year
% (avoids a short momentum position from sneaking into value strategies)
load me
bm = BE./lag(me,6,nan); % I like to keep the negative BM firms, some don't

% The assets of financial firms are very different (and larger than) those
% of other firms; when we scale by assets we'll often want to kick out 
% financials
load SIC
FinFirms = (SIC >= 6000).*(SIC <= 6999);


% Store and clean up
save([dataPath, 'PS.mat'],'PS');
save([dataPath, 'BE.mat'],'BE');
save([dataPath, 'bm.mat'],'bm');
save([dataPath, 'FinFirms.mat'],'FinFirms');
clearvars -except dataPath Params

% Replicate hml
load ret
load me
load bm
load dates
load NYSE
load ff
const = .01*ones(size(hml));

% Fama and French kick out negative book-equity firms (the most growth-y
bm(bm < 0) = nan; 
ind = makeBivSortInd(me,2,bm,[30 70],'breaksFilter',NYSE);   

% Carries over all {'Name','Value'} optional inputs from runUnivSort 
% without 'addLongShort'
[res,~] = runBivSort(ret,ind,2,3,dates,me,'printResults',0); 

% Replicate HML from the corner portfolios 
hmlrep = ( res.pret(:,3) + res.pret(:,6) ...
          - res.pret(:,1) - res.pret(:,4) )/2;

% Should see a high (~99%) correlation, but it WON'T match perfectly, 
% for a couple of reasons. Fama-French construct the variable using data 
% available at the time of construction (they don't go back and change it 
% if they fix data errors in crsp/compustat). It shouldn't matter: "value" 
% is a robust phenomena-- one of the reasons it's important is that the 
% details don't "matter" for getting a real "exposure" to value

% Let the user know of the check
fprintf('Compare our HML with HML from Ken French''s website:\n');

% Correlation shoud be >95%
index = isfinite(sum([hmlrep hml],2));
corrcoef([hmlrep(index) hml(index)]) 

% Mean return to either factor should be ~0.31 %/mo.
prt(nanols(hml,[const])) 
prt(nanols(hmlrep,[const]))

% Should see high R-squared
prt(nanols(hml,[const hmlrep]))
prt(nanols(hmlrep,[const hml]))

% Clean up the workspace
clearvars -except dataPath Params

% Make quarterly book equity. Start with shareholder's equity
load SEQQ
load CEQQ
load PSTKQ
load ATQ
load LTQ
SE = SEQQ;                              % shareholder equity
temp = CEQQ + PSTKQ;
SE(isnan(SE)) = temp(isnan(SE));        % uses common equity + preferred stock if SEQ is missing
temp = ATQ - LTQ;
SE(isnan(SE)) = temp(isnan(SE));        % uses assets - liabilities, if others are missing

% Load preferred stock
load PSTKQ
PS = PSTKQ; 

% Load deferred taxes
load TXDITCQ
DT = TXDITCQ; 

% Book equity is shareholder equity + deferred taxes - preferred stock
BEQ = nanmatsum(SE, nanmatsum(DT, -PS)); 
save([dataPath, 'BEQ.mat'],'BEQ');
clearvars -except dataPath Params

% Make quarterly gross profitability
load REVTQ
load COGSQ
GPQ = REVTQ - COGSQ;
save([dataPath, 'GPQ.mat'],'GPQ');
clearvars -except dataPath Params

% Make quarterly return-on-assets
load IBQ
load ATQ
roa = IBQ./lag(ATQ,3,nan);
save([dataPath, 'roa.mat'],'roa');
clearvars -except dataPath Params

% SUE and dROE
load IBQ
load EPSPXQ
load BEQ
load dates
load RDQ

% Find the report dates
idxRprtDate = (IBQ ~= lag(IBQ,1,nan)).*isfinite(IBQ);

% Initialize a few variables for the quarterly lags
BEQL1 = nan(size(IBQ));
IBQL4 = nan(size(IBQ));
epsStruct = struct;
for i=1:12
    epsStruct(i).lagEPSPXQ = nan(size(IBQ));
end

%  Create IBQ and EPSPXQ only for the report dates
IBQL0 = IBQ;
IBQL0(idxRprtDate == 0) = nan;
EPSPXQL0 = EPSPXQ;
EPSPXQL0(idxRprtDate == 0) = nan;

% Initiate the index of the number of lagged report dates available
numLagIdx = idxRprtDate;

% Loop over the past 60 months
for i = 1:60
    
    % Add the lagged index
    numLagIdx = numLagIdx + idxRprtDate .* lag(idxRprtDate, i, 0);
    thisNumLagIdx = numLagIdx .* lag(idxRprtDate, i, 0);
    
    lIBQ = lag(IBQ,i,0);
    lBEQ = lag(BEQ,i,0);
    lEPSPXQ = lag(EPSPXQ,i,0);
    
    IBQL4(thisNumLagIdx == 5) = lIBQ(thisNumLagIdx == 5);
    BEQL1(thisNumLagIdx == 2) = lBEQ(thisNumLagIdx == 2);   
    
    for j=1:12
        epsStruct(j).lagEPSPXQ(thisNumLagIdx == j+1) = lEPSPXQ(thisNumLagIdx == j+1);
    end
end

% Initiate several variables
qmin = 6;
startDate = find(dates >= 197101, 1, 'first');
nMonths = size(IBQ,1);
SUE = nan(size(IBQ));

% Loop over the months
for i = startDate:nMonths
    % Get the lagged 8 quarters of EPS
    temp = [];
    for j=1:8
        temp = [temp; epsStruct(j).lagEPSPXQ(i,:) - epsStruct(j+4).lagEPSPXQ(i,:)];
    end
    
    % Take the standard deviation for those for which we have more than
    % qmin observations out of these 8
    stemp = sum(isfinite(temp),1);
    temp = nanstd(temp);
    temp(stemp < qmin) = nan;
    temp(temp == 0) = nan;
    
    % Calculate SUE as (EPS_t - EPS_{t-4})/std(dEPS_{t-8:t})
    SUE(i,:) = (EPSPXQL0(i,:)-epsStruct(4).lagEPSPXQ(i,:))./temp;
end

% Fill in the months in between announcements 
SUE = FillMonths(SUE);

% Store SUE
save([dataPath, 'SUE.mat'],'SUE');

% Create and store dROE and clean up the workspace
dROE = FillMonths((IBQL0 - IBQL4)./BEQL1);
save([dataPath, 'dROE.mat'],'dROE');
clearvars -except dataPath Params

% Make SUE2 -- simpler construction
% current earnings minus earnings from one year ago, scaled by the standard
% deviation of the last eight quarterly earnings
load dates
load IBQ
SUE2 = nan(size(IBQ));
for i = max(find(dates >= 197101, 1, 'first'),25):size(IBQ, 1)
    SUE2(i,:) = (IBQ(i,:)-IBQ(i-12,:))./nanstd(IBQ(i-24:3:i-3,:));
end
save([dataPath, 'SUE2.mat'],'SUE2');
clearvars -except dataPath Params

% Make dROA -- difference between current earnings and average of the last 
% fourquarters, scaled by lagged assets
load ATQ
load IBQ
load dates

dROA = nan(size(IBQ));
startDate = find(dates==197101);
nMonths = size(IBQ,1);
for i = startDate:nMonths
    dROA(i,:) = IBQ(i,:) - nanmean(IBQ(i-12:i-1,:));
end
dROA = dROA./ATQ;
save([dataPath, 'dROA.mat'],'dROA');
clearvars -except dataPath Params

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
save([dataPath, 'amonth.mat'],'amonth');
clearvars -except dataPath Params

% Timekeeping
fprintf('COMPUSTAT derived variables run ended at %s.\n', char(datetime('now')));

