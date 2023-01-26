function makeBetas(Params)
% PURPOSE: This function creates the beta signals used in Novy-Marx and
% Velikov (2022) 
%------------------------------------------------------------------------------------------
% USAGE:   
% makeBetas(Params)              % Turns the CRSP daily file into matrices
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.domComEqFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.COMPVarNames - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.tcostsType - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeBetas(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Frazzini, A. and L. Pedersen, 2014, Betting against beta, Journal of
%  Financial Economics, 111 (1): 1-25
%  2. Novy-Marx, R. and M. Velikov, 2022, Betting against betting against
%  beta, Journal of Financial Economics, 143 (1): 80-106.
%  3. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on making the betas. Run started at %s.\n\n',char(datetime('now')));

% Store the general data path
dataPath = [Params.directory, 'Data', filesep];

% Start with the Frazzini - Pedersen betas
fprintf('Making Frazzini-Pedersen (2014) betas first.\n');
load dret
load ff
load dff
load ret
load dates
load ddates

% Store a few constants
nStocks = size(ret, 2);

% Store the excess stock returns
rptdRf = repmat(drf, 1, nStocks);
dxret = dret - rptdRf;

% initialize the beta
beta = nan(size(ret));

% Store the 3-day excess returns and market returns
dret3 = (1+dxret) .* (1+lag(dxret,1,nan)) .* (1+lag(dxret,2,nan)) - 1;
dmkt3 = (1+dmkt)  .* (1+lag(dmkt,1,nan))  .* (1+lag(dmkt,2,nan))  - 1;

% Determine the start and length row indices
startDate = find(dates >= (100*(Params.SAMPLE_START+3)+1), 1, 'first');
endDate = length(dates);

for i = startDate:endDate
        
    % Find the daily dates over the past year
    daysPastYear = find( floor(ddates/100) >= dates(max(i-11, 1)) & ...
                         floor(ddates/100) <= dates(i));

    % Find the daily dates over the past 60 months
    daysPast5Years = find( floor(ddates/100) >= dates(max(i-59, 1)) & ...
                           floor(ddates/100) <= dates(i));
    
    % Find the stocks that satisfy the FP filters (750 3-day returns over
    % the past 5 years; 120 daily returns over the past year; daily return
    % last trading day)
    stocksInMonth = find( sum(isfinite(dret3(daysPast5Years, :)) ,1) >= 750 &  ...
                          sum(isfinite(dxret(daysPastYear, :)), 1) >= 120  & ...
                              isfinite(dxret(daysPastYear(end), :)));    
    nStocksInMonth = length(stocksInMonth);

    % Loop over the stocks
    for k = 1:nStocksInMonth
        % Store the column corresponding to the current stock
        j = stocksInMonth(k);
        
        % Store the 3-day returns for the correlation estimation (5 years)
        rtrnSeries = [log(1+dret3(daysPast5Years,j)) ... % 3-day stock return
                      log(1+dmkt3(daysPast5Years))];     % 3-day market return           
        
        % Drop nan or imaginary numbers
        idxToDrop = (isnan(sum(rtrnSeries,2))) | ...
                    (sum(imag(rtrnSeries) ~= 0, 2) > 0);
        rtrnSeries(idxToDrop,:)=[];     
        
        % Store the daily returns for standard deviations estimation
        % (1-year)
        dailyRtrnSeries = [log(1+dxret(daysPastYear,j)) ... % Daily stock return
                           log(1+dmkt(daysPastYear))];      % Daily market return

        % Drop nan or imaginary numbers
        idxToDrop = (isnan(sum(dailyRtrnSeries,2))) | ...
                    (sum(imag(dailyRtrnSeries) ~= 0, 2) > 0);
        dailyRtrnSeries(idxToDrop,:)=[];

        % Calculate the standard deviations, correlation, and beta
        stdev = std(dailyRtrnSeries, 1, 1); 
        rho = corr(rtrnSeries);     
        beta(i,j) = rho(1,2) * stdev(1) / stdev(2);        
    end
end

% Apply the shrinkage towards 1
bfp = 0.6*beta + 0.4*1; 

fprintf('Making the rest of the betas next.\n');

% Iniatialize the matrices for the rest of the betas 
bols = nan(size(ret)); % Ivo's OLS benchmark - 1 year of daily data, 1 mkt lag, no shrinkage
bdim = nan(size(ret)); % Dimson correction - add one more lag of mkt
bvck = nan(size(ret)); % Vasicek shrinkage, similar to what LSY use
bstd = nan(size(ret)); % What we would consider standard - 1 mkt lag, shrinkage to 1
bsw  = nan(size(ret)); % Ivo Welch's betas

% Initialize the matrix for the standard errors of the OLS betas
bolsserr = nan(size(ret)); 

% Store the lagged daily market excess return  vector
dmktL1 = lag(dmkt,1,nan);

% Store the market bounds for Ivo Welch's betas
dmktBounds=[min([-2*dmkt 4*dmkt],[],2) max([-2*dmkt 4*dmkt],[],2)];

% Apply the market bounds to the excess return matrix for Ivo Welch's betas
dxretw = max(dxret, repmat(dmktBounds(:,1), 1, nStocks));
dxretw = min(dxretw, repmat(dmktBounds(:,2), 1, nStocks));

% Initialize the weights for the Vasicek shrinkage
wvck = nan(size(ret)); 

% Determine the start and length row indices
startDate = find(dates >= (100*(Params.SAMPLE_START+1)+1), 1, 'first');
endDate = length(dates);

for i = startDate:endDate
    % Find the daily dates over the past year
    daysPastYear = find( floor(ddates/100) >= dates(max(i-11, 1)) & ...
                         floor(ddates/100) <= dates(i));

    % Find the stocks that satisfy a basic filter (120 daily returns over 
    % the past year; daily return last trading day available)
    stocksInMonth = find( sum(isfinite(dxret(daysPastYear, :)), 1) >= 120  & ...
                              isfinite(dxret(daysPastYear(end), :)));    
    nStocksInMonth = length(stocksInMonth);
    
    % Store the RHS matrices for the beta estimation regressions
    x1 = [ones(size(daysPastYear)) dmkt(daysPastYear)];
    x2 = [ones(size(daysPastYear)) dmkt(daysPastYear) dmktL1(daysPastYear)];
    
    % Loop over the stocks
    for k = 1:nStocksInMonth
        % Store the column corresponding to the current stock
        j = stocksInMonth(k);
        
        % Store the excess returns for this particular stock
        y = dxret(daysPastYear,j);
        
        % Benchmark OLS beta
        res = nanols(y, x1);  
        bols(i,j) = res.beta(2);         
        bolsserr(i,j) = res.bstd(2); % For the Vasicek

        % Dimson correction - add 1 lag of mkt 
        res = nanols(y, x2); 
        bdim(i,j) = res.beta(2) + res.beta(3);
        
        % Ivo's betas - use the winsorized returns (dxretw) 
        res = nanols(dxretw(daysPastYear,j), x1); 
        bsw(i,j) = res.beta(2);
    end
    
    % Apply the Vasicek shrinkage
    sigmaSqI = bolsserr(i,:) .^ 2;
    sigmaSqT = std(bols(i,:),'omitnan')^2;
    wvck(i,:) = sigmaSqT ./ (sigmaSqT + sigmaSqI);
    bvck(i,:) = wvck(i,:) .* bols(i,:) + (1-wvck(i,:)) * mean(bols(i,:),'omitnan');
    
    % Apply a simple shrinkage to the Dimson estimate
    bstd = 0.6*bdim + 0.4*1;
end

% Store the betas
save([dataPath,'betas.mat'],'bols','bdim','bsw','bvck','bstd','bfp');
save([dataPath,'bols.mat'],'bols');
save([dataPath,'bdim.mat'],'bdim');
save([dataPath,'bsw.mat'],'bsw');
save([dataPath,'bvck.mat'],'bvck');
save([dataPath,'bstd.mat'],'bstd');
save([dataPath,'bfp.mat'],'bfp');

% Timekeeping
fprintf('\nBeta construction run ended at %s.\n', char(datetime('now')));

