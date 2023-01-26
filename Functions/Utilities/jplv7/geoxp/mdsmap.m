function [out]=mdsmap(long,lat,dataset,varargin)
% PURPOSE: This function links a map and mds analysis
%------------------------------------------------------------------------
% USAGE: out=mdsmap(long,lat,dataset,p,restarts,normflag,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           dataset = n x p matrix of the variables to study
%           p = optional number of dimensions into which points are to be mapped
%               [default = 2].
%           restarts = optional number of restarts, after finding a new minimum stress,
%                    needed to end search [default=0].
%           normflag = optional boolean flag indicating that stress is to be normalized 
%                    to a range [0-1] if true (=1), or unnormalized
%                    sum-of-squared deviations if false (=0) [default = 0].
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on the map or the mds plot by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         Selection is lost when you click on the map
%         To quit, click the middle button or press 'q'
%------------------------------------------------------------------------
% uses mds.m, selectmap.m, selectstat.m
%------------------------------------------------------------------------
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
p=2;
symbol=0;
restarts=0;
normflag=0;
vectx=[];
vecty=[];


%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save mdsfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%



% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        p=varargin{1};
    end;
    
    if t>=2 & ~isempty(varargin{2})
        restarts=varargin{2};
    end;
    if t>=3 & ~isempty(varargin{3})
        normflag=varargin{3};
    end;
    if t>=4 & ~isempty(varargin{4})
        carte=varargin{4};
        c=1;
    end;
    if t>=5 & ~isempty(varargin{5})
        label=varargin{5};
        l=1;
    end;  
    if t==6 & ~isempty(varargin{6})
        symbol=varargin{6};
    end;
end;

%%%%%%%%%%%%%%%%%%%%%


% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Trace the mds plot
H=sparse(length(dataset(:,1)),length(dataset(:,1)));
for i=1:size(dataset,2)
    Tp1=repmat(dataset(:,i)',length(dataset(:,i)),1);
    Tp2=repmat(dataset(:,i),1,length(dataset(:,i)));
    H=H+(Tp2-Tp1).^2;
end;
H=sqrt(H);
[crd,stress,mapdist]=mds(H,'',p,restarts,normflag,1);
Axis2=subplot(1,2,2);
plot(crd(:,1),crd(:,2),'b.');
title('Mds Plot');
axis manual;
subplot(Axis1);
axis manual;

Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
maptest=0;
scattertest=0;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iunselect)
      plot(crd(Iunselect,1),crd(Iunselect,2),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(crd(Iselect,1),crd(Iselect,2),'b*');
            else
                plot(crd(Iselect,1),crd(Iselect,2),'r.');
            end;
        elseif scattertest==1
            if symbol==1
                plot(crd(Iselect,1),crd(Iselect,2),'bo'); 
            else
                plot(crd(Iselect,1),crd(Iselect,2),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        end;
    end;
    
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;    
    
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'b*');
            else
                plot(long(Iselect),lat(Iselect),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif scattertest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'bo');
            else
                plot(long(Iselect),lat(Iselect),'m.');              
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    
    
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            scattertest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % scatterplot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if scattertest==0
            scattertest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            
            obs=selectstat('scatter',obs,crd(:,1),'point',crd(:,2),x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectstat('scatter',obs,crd(:,1),'poly',crd(:,2),x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%