function combStrats = makeCombStrats(filledAnoms, filledSignal, keepRollAnoms, resAnoms, resBasicSorts, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals and runs 
% univariate sorts.
%------------------------------------------------------------------------------------------
% USAGE:   
% combStrats = makeCombStrats(filledAnoms, filledSignal, keepRollAnoms, resAnoms, resBasicSorts, timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - filledAnoms - matrix (nMonths x nStocks) with filled-in test 
%                        signal
%        - keepRollAnoms - matrix (nMonths x nAnoms) indicating whether an
%                          anomaly has had more than 40% of market cap
%                          observations in the average month over the past
%                          10 years.
%        - resAnoms - vector (nAnoms x 1) of structures containing the
%                     univariate sort results
%        - resBasicSorts - vector (nAnoms x 1) of structures with univariate
%                          sort results
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - combStrats - structure (nCombMethods x 2) with combination
%                       strategy results
%        - signalLabel - a cell array with a character string containing a
%                       label for the test signal
%------------------------------------------------------------------------------------------
% Examples:
%
% combStrats = makeCombStrats(filledAnoms, filledSignal, keepRollAnoms, resAnoms, resBasicSorts, timePeriod);
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeAverageRank(), makeWeightedAverageRank(), makeFMBRes(), 
%       makePLSRes(), makeIPCARes(), makeLassoRes(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on combination strategy returns. Run started at %s.\n', char(datetime('now')));

% Load some variables
load me
load dates
load ret
load ff

% Start the counter
count = 1;

% Try the average rank
try
    combStrats(count,1).eret = makeAverageRank(filledAnoms, me); 
    combStrats(count,1).eret_enh = makeAverageRank(cat(3, filledAnoms, filledSignal), me); 
    combStrats(count,1).label = 'Average rank';
    combStrats(count,1).explanation = cellstr(['This method sorts stocks on the basis of forecast excess returns, where ', ...
                                       'these are calculated on the basis of their average cross-sectional ', ...
                                       'percentile rank across return predictors, and the predictors are all ', ...
                                       'signed so that higher ranks are associated with higher average returns. ']);    
    count = count + 1;
catch ME
    combStrats(count,1).eret = nan(size(ret));
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).label = 'Average rank - N/A';
    combStrats(count,1).errorObject = ME;
    count = count + 1;
end

% Try the weighted average rank
try
    % Store the portfolio returns for the anomalies
    s = find(dates==timePeriod(1));
    e = find(dates==timePeriod(2));
    nAnoms = size(filledAnoms, 3);
    pret = nan(length(dates), nAnoms);
    for i = 1:nAnoms
        pret(s:e, i) = resAnoms(i).pret(s:e,end);    
    end
    pret(s:e, nAnoms+1) = resBasicSorts(1,1).res.pret(s:e,end);
    combStrats(count,1).eret = makeWeightedAverageRank(filledAnoms, pret(:, 1:end-1), me, dates, timePeriod);
    combStrats(count,1).eret_enh = makeWeightedAverageRank(cat(3, filledAnoms, filledSignal), pret, me, dates, timePeriod);
    combStrats(count,1).label = 'Weighted-Average rank';
    combStrats(count,1).explanation = cellstr(['This method sorts stocks on the basis of forecast excess returns, where ', ...
                                       'these are calculated as weighted-average cross-sectional ', ...
                                       'percentile rank across return predictors, and the predictors are all ', ...
                                       'signed so that higher ranks are associated with higher average returns and the ', ...
                                       'weights are determined by the average returns over the past ten years to  the ', ...
                                       'long/short strategies based on the individual signals. ']);        
    count = count + 1;
catch ME
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).label = 'Weighted-Average rank - N/A';
    combStrats(count,1).errorObject = ME;
    count = count + 1;
end


% Try the Fama-MacBeth
try
    combStrats(count,1).eret = makeFMBRes(filledAnoms, dates, timePeriod,ret);
    combStrats(count,1).eret_enh = makeFMBRes(cat(3, filledAnoms, filledSignal), dates, timePeriod,ret);
    combStrats(count,1).label = 'Fama-MacBeth';
    combStrats(count,1).explanation = cellstr(['This method sorts stocks on the basis of forecast excess returns, where ', ...
                                       'these are calculated from \\citet{FamaMacBeth1973} regressions following ', ...
                                       '\\citet{HaugenBaker1996} and \\citet{Lewellen2015} using only data in the investor''s ', ...
                                       'information set at the time of portfolio formation. The estimation uses rolling ', ...
                                       'ten years of data, so the actual strategies begin ten years later for this combination method.  ']);        
    count = count + 1;
catch ME
    combStrats(count,1).eret = nan(size(ret));
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).label = 'Fama-MacBeth - N/A';
    combStrats(count,1).errorObject = ME;
    count = count + 1;
    
end

% Try the Partial Least Squares
try
    combStrats(count,1).eret =  makePLSRes(filledAnoms, dates, timePeriod, ret);
    combStrats(count,1).eret_enh =  makePLSRes(cat(3, filledAnoms, filledSignal), dates, timePeriod, ret);
    combStrats(count,1).label = 'Partial Least Squares';
    combStrats(count,1).explanation = cellstr(['This method sorts stocks on the basis of forecast excess returns, where ', ...
                                       'these are calculated from partial least squares (PLS) filtering procedure following ', ...
                                       '\\citet*{LightMaslovRytchkov2017} using only data in the investor''s ', ...
                                       'information set at the time of portfolio formation. The estimation uses rolling ', ...
                                       'ten years of data, so the actual strategies begin ten years later for this combination method.  ']);        
    count = count + 1;    
catch ME
    combStrats(count,1).eret = nan(size(ret));
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).label = 'Partial Least Squares - N/A';
    combStrats(count,1).errorObject = ME;
    count = count + 1;    
end



% Try the IPCA
try
    combStrats(count,1).eret = makeIPCARes(filledAnoms, keepRollAnoms, ret, rf, dates, timePeriod);    
    combStrats(count,1).eret_enh = makeIPCARes(cat(3, filledAnoms, filledSignal), [keepRollAnoms true(size(dates))], ret, rf, dates, timePeriod);
    combStrats(count,1).label = 'IPCA';
    combStrats(count,1).explanation = cellstr(['This method sorts stocks on the basis of forecast excess returns, where ', ...
                                       'these are calculated from  the instrumented principal component analysis (IPCA) procedure of ', ...
                                       '\\citet*{KellyPruittSu2019} using only data in the investor''s ', ...
                                       'information set at the time of portfolio formation. The estimation uses rolling ', ...
                                       'ten years of data, so the actual strategies begin ten years later for this combination method.  ']);  
    count = count + 1;
catch ME
    combStrats(count,1).eret = nan(size(ret));
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).label = 'IPCA - N/A';
    combStrats(count,1).errorObject = ME;
    count = count + 1;
end



% Try the LASSO
try
    combStrats(count,1).eret = makeLassoRes(filledAnoms, ret, dates, timePeriod);
    combStrats(count,1).eret_enh = makeLassoRes(cat(3, filledAnoms, filledSignal), ret, dates, timePeriod);
    combStrats(count,1).label = 'LASSO';
    combStrats(count,1).explanation = cellstr(['This method sorts stocks on the basis of forecast excess returns, where ', ...
                                       'these are estimated by least absolute shrinkage and selection operator (LASSO) ', ...
                                       'using only data in the investor''s information set at the time of portfolio formation. ', ...
                                       'Following \\citet*{ChenVelikov2022}, LASSO penalty ($\\lambda$) is selected ', ...
                                       'by minimizing the mean squared error (MSE) estimated by 5-fold cross validation. ', ...
                                       'The estimation uses rolling ten years of data, so the actual strategies begin ten ', ...
                                       'years later for this combination method.  ']);       
%     count = count + 1;
catch ME
    combStrats(count,1).eret = nan(size(ret));
    combStrats(count,1).eret_enh = nan(size(ret));
    combStrats(count,1).label = 'LASSO - N/A';
    combStrats(count,1).errorObject = ME;
%     count = count + 1;
    
end

% Timekeeping
fprintf('\nDone with combination strategy results at %s.\n\n', char(datetime('now')));
